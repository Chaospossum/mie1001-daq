// DAQ shield mass scan: MCP4725 mass command -> Extrel QPS, Faraday-cup preamp -> ADS1115
// MIE1001 Team 5.  For the SHIELD (hardware/mie1001_daq_simple, rev E with JP1), not the breadboard.
//
// Shield connections used here
//   ADS1115 @0x48    A0 = SIGNAL IN (J1, 4k7/100nF)          (not used by this sketch)
//                    A1 = PRE_OUT (LMP7721 TIA -> R11 1k / C6 1uF)
//                    A2 = QPS_OUT readback through JP1 (bridged by default)
//                    A3 = VREF (~2.5 V, buffered divider)
//                    ALRT -> D2 (INT0), used as the conversion-ready (RDY) pulse
//   MCP4725 @0x60    OUT -> J2 QPS OUT, 0-5 V mass command (NOT the library default 0x62)
//   TRIG IN (J3)  -> D8, active HIGH (R3 pulls it low when open)
//   D9 is free.
//
// Preamp and SIGN CONVENTION
//   TIA: Rf = 100 MOhm, Cf = 10 pF, non-inverting input at VREF.  V_A1 = VREF - I * Rf.
//   We read V_diff = V_A1 - V_A3 with the ADS1115's differential pair 1-3, and report
//       I = -(V_diff - V_offset) / Rf
//   I > 0 means POSITIVE CURRENT INTO THE INPUT = positive ions landing on the Faraday cup.
//   A positive-ion beam therefore drives PRE_OUT BELOW VREF (V_diff < 0) and gives I_pA > 0.
//   Range about +/-24 nA (output swings ~+/-2.4 V around VREF).
//   GAIN_ONE  (+/-4.096 V): 125 uV/count = 1.25 pA/count  (default, full preamp range)
//   GAIN_FOUR (+/-1.024 V): 31.25 uV/count = 0.31 pA/count (clips at about +/-10 nA)
//
// Mains (50 Hz) rejection
//   The ADS1115 runs CONTINUOUSLY at 250 SPS, paced by the RDY pulse on D2.  Five back-to-back
//   conversions = one whole 20 ms mains period (a boxcar with nulls at 50, 100, 150 Hz ...).
//   Each point averages n_avg such windows.  250 SPS is the only ADS1115 rate that fits a whole
//   number of conversions in 20 ms.  The ADS clock is only +/-10 % accurate, so the window is
//   18-22 ms worst case; 'i' measures the real rate and prints the real window length.
//
// Settling
//   R6*C2 (100M*10p) and R11*C6 (1k*1u) are two ~1 ms poles: after a DAC step the first kept
//   preamp conversion must START >= SETTLE_MS (15 ms) after the step.  Every ADS mux/gain change
//   throws away one conversion.  The A2 read-back is done INSIDE the settling time, so it is free.
//
// TIMING BUDGET PER POINT (250 SPS = 4.0 ms/conversion nominal, I2C at 400 kHz, n_avg = 1)
//   DAC write (4 bytes)                                         0.1 ms
//   A2 read-back: config write 0.3 + 1 discard + 2 kept conv   12.3 ms  } overlaps the 15 ms
//   A1-A3: config write 0.3 + 1 discard conv                     4.3 ms  } settle (ends at ~16.7)
//   (extra discards only if the ADS clock runs >10 % fast)
//   preamp: 5 conversions x n_avg                               20.0 ms x n_avg
//   serial: ~40 chars = 3.5 ms at 115200, but interrupt-driven from the 64-byte TX buffer, so it
//           runs during the next point's settle; only ~0.5 ms CPU for float formatting
//   ---------------------------------------------------------------------------------------
//   total ~ 17 + 20 * n_avg ms   ->  n_avg=1: ~37 ms/point,  n_avg=4: ~97 ms/point
//   2600 points: n_avg=1 ~ 96 s (1.6 min)   n_avg=2 ~ 2.5 min   n_avg=4 ~ 4.2 min
//   (+/-10 % with the ADS clock).  Without JP1 (JP1_BRIDGED = false) the A2 read is skipped,
//   but the 15 ms settle still dominates, so the time per point is the same.
//
// Serial: 115200 baud, Newline.  Commands:
//   z [save]                zero: average the preamp (beam OFF) 0.5 s, store the offset; 'save' -> EEPROM
//   s <start> <stop> <step> [n_avg]   scan DAC codes (0-4095, either direction), CSV out
//   t [<start> <stop> <step> [n_avg]] arm, wait for a rising edge on D8 (TRIG IN), then scan
//                                      (no arguments = the last scan's settings)
//   r [n_avg]               read once at the present DAC code
//   d <code>                set the DAC code (0-4095)
//   g <gain>                preamp ADS gain: 2/3, 1 (default), 2, 4, 8, 16
//   i                       I2C scan + self-check, prints PASS/FAIL
//   h or ?                  help
//   Any character sent during a scan or while armed aborts it.
//
// Output: comment lines start with '#', data lines are CSV:
//   code,V_cmd,I_pA,V_diff[,mass_amu]
//   V_cmd  = QPS_OUT read back on A2 (V), I_pA = offset-corrected current (pA),
//   V_diff = raw V_A1 - V_A3 (V, not offset-corrected).  mass_amu only when AMU_PER_VOLT > 0.
//
// Libraries: Adafruit ADS1X15 (2.x), Adafruit MCP4725.  Board: Arduino Uno.

#include <Wire.h>
#include <avr/eeprom.h>
#include <Adafruit_ADS1X15.h>
#include <Adafruit_MCP4725.h>

// ---------------------------------------------------------------- configuration
const uint8_t  ADS_ADDR = 0x48;
const uint8_t  DAC_ADDR = 0x60;        // NOT the library default (0x62)
const uint8_t  RDY_PIN  = 2;           // ADS ALRT/RDY, INT0, 10k pull-up on the breakout
const uint8_t  TRIG_PIN = 8;           // TRIG IN, active HIGH
const bool     JP1_BRIDGED = true;     // JP1 connects QPS_OUT to ADS A2; set false if cut

const float    RF_OHM    = 100e6;      // R6 feedback resistor
const uint16_t SETTLE_MS = 15;         // after a DAC step, before the first kept preamp conversion
const uint8_t  SAMPLES_PER_WINDOW = 5; // 5 x 4 ms = 20 ms = one 50 Hz period at 250 SPS
const uint16_t CONV_TIMEOUT_US = 6000; // no RDY pulse within this -> RDY fault (nominal 4000)
const uint8_t  N_CMD_READS = 2;        // kept A2 conversions per point
const uint8_t  ZERO_WINDOWS = 25;      // 'z' averages 25 x 20 ms = 0.5 s

// Mass command scale.  The Extrel 150-QC wants 0-10 V; a x2 stage will follow QPS OUT later.
// amu = V_cmd(A2) * QPS_STAGE_GAIN * AMU_PER_VOLT.  AMU_PER_VOLT is UNCONFIRMED: leave 0 to
// omit the mass column, fill it in once Team 4 confirms the controller's volts-per-amu.
const float    QPS_STAGE_GAIN = 1.0;   // 2.0 once the x2 stage is fitted (if A2 still reads the DAC side)
const float    AMU_PER_VOLT   = 0.0;   // amu per volt AT THE EXTREL INPUT; 0 = not known yet
const float    DAC_VDD_NOM    = 5.0;   // only used for V_cmd when JP1 is cut

const uint16_t EE_MAGIC = 0x5A17;
EEMEM uint8_t   eeSlot[8];             // EEPROM bytes 0-7 (magic, offset, gain)
struct EeData { uint16_t magic; float offsetV; uint8_t gainIdx; };

// ---------------------------------------------------------------- state
Adafruit_ADS1115 ads;
Adafruit_MCP4725 dac;

const adsGain_t GAINS[6] = { GAIN_TWOTHIRDS, GAIN_ONE, GAIN_TWO, GAIN_FOUR, GAIN_EIGHT, GAIN_SIXTEEN };
const float     GAIN_FS[6] = { 6.144, 4.096, 2.048, 1.024, 0.512, 0.256 };
uint8_t  gainIdx  = 1;                 // GAIN_ONE
float    offsetV  = 0;                 // preamp V_diff with the beam off
uint16_t dacCode  = 0;
bool     rdyFault = false;

uint16_t scanStart = 0, scanStop = 4095, scanStep = 1;
uint8_t  scanAvg = 1;

volatile uint8_t  rdyCount = 0;
volatile uint32_t rdyTime  = 0;
void onRdy() { rdyCount++; rdyTime = micros(); }

// ---------------------------------------------------------------- ADS helpers
// Start continuous conversions on a mux setting; forget any pending RDY pulses.
void startMux(uint16_t mux, adsGain_t gain) {
  ads.setGain(gain);
  ads.startADCReading(mux, /*continuous=*/true);   // also puts ALRT into RDY mode
  noInterrupts(); rdyCount = 0; interrupts();
}

// Wait for the next finished conversion and return it.  *tEnd = when it finished (micros).
int16_t nextConv(uint32_t *tEnd = nullptr) {
  uint32_t t0 = micros();
  while (rdyCount == 0) {
    if (micros() - t0 > CONV_TIMEOUT_US) { rdyFault = true; break; }
  }
  noInterrupts();
  if (rdyCount) rdyCount--;
  uint32_t t = rdyTime;
  interrupts();
  if (tEnd) *tEnd = rdyFault ? micros() : t;
  return ads.getLastConversionResults();
}

float lsbVolts() { return GAIN_FS[gainIdx] / 32768.0; }
float pAperCount() { return lsbVolts() / RF_OHM * 1e12; }

// ---------------------------------------------------------------- one point
struct Point { float vCmd; float vDiff; bool ovr; };

// stepDac: write the DAC first and wait out the settling; otherwise just read.
Point measure(uint16_t code, uint8_t nAvg, bool stepDac) {
  Point p;
  uint32_t tStep = micros();
  if (stepDac) { dac.setVoltage(code, false); dacCode = code; tStep = micros(); }

  if (JP1_BRIDGED) {                                 // read back the real command, during the settle
    startMux(ADS1X15_REG_CONFIG_MUX_SINGLE_2, GAIN_TWOTHIRDS);
    nextConv();                                      // discard after the mux change
    long s = 0;
    for (uint8_t k = 0; k < N_CMD_READS; k++) s += nextConv();
    p.vCmd = (float)s / N_CMD_READS * (6.144 / 32768.0);
  } else {
    p.vCmd = dacCode * (DAC_VDD_NOM / 4096.0);
  }

  startMux(ADS1X15_REG_CONFIG_MUX_DIFF_1_3, GAINS[gainIdx]);
  uint32_t tEnd;
  nextConv(&tEnd);                                   // discard after the mux change
  if (stepDac)                                       // next conversion must START >= SETTLE_MS after the step
    while (tEnd - tStep < (uint32_t)SETTLE_MS * 1000UL && !rdyFault) nextConv(&tEnd);

  long s = 0;
  p.ovr = false;
  uint16_t n = (uint16_t)SAMPLES_PER_WINDOW * nAvg;  // whole 20 ms windows, back to back
  for (uint16_t k = 0; k < n; k++) {
    int16_t c = nextConv();
    if (c >= 32760 || c <= -32760) p.ovr = true;
    s += c;
  }
  p.vDiff = (float)s / n * lsbVolts();
  return p;
}

float currentpA(float vDiff) { return -(vDiff - offsetV) / RF_OHM * 1e12; }

void printPoint(uint16_t code, const Point &p) {
  Serial.print(code);            Serial.print(',');
  Serial.print(p.vCmd, 4);       Serial.print(',');
  Serial.print(currentpA(p.vDiff), 2); Serial.print(',');
  Serial.print(p.vDiff, 6);
  if (AMU_PER_VOLT > 0) { Serial.print(','); Serial.print(p.vCmd * QPS_STAGE_GAIN * AMU_PER_VOLT, 2); }
  Serial.println();
}

void printColumns() {
  Serial.print(F("code,V_cmd,I_pA,V_diff"));
  Serial.println(AMU_PER_VOLT > 0 ? F(",mass_amu") : F(""));
}

void printGain() {
  Serial.print(F("# gain ")); Serial.print(gainIdx == 0 ? F("2/3") : F(""));
  if (gainIdx) Serial.print(1 << (gainIdx - 1));
  Serial.print(F(": +/-")); Serial.print(GAIN_FS[gainIdx], 3);
  Serial.print(F(" V, ")); Serial.print(pAperCount(), 3);
  Serial.print(F(" pA/count, clips at +/-"));
  Serial.print(min(GAIN_FS[gainIdx], 2.4) / RF_OHM * 1e9, 2); Serial.println(F(" nA"));
}

bool abortRequested() {
  if (!Serial.available()) return false;
  while (Serial.available()) Serial.read();
  return true;
}

// ---------------------------------------------------------------- scan
void scan(uint16_t start, uint16_t stop, uint16_t step, uint8_t nAvg, bool triggered) {
  uint16_t nPts = (start <= stop ? stop - start : start - stop) / step + 1;
  int8_t dir = start <= stop ? 1 : -1;

  dac.setVoltage(start, false); dacCode = start;     // pre-position so the first point is settled

  if (triggered) {
    Serial.println(F("# armed: waiting for a rising edge on TRIG IN (D8); send any key to abort"));
    while (digitalRead(TRIG_PIN)) if (abortRequested()) { Serial.println(F("# aborted")); return; }
    while (!digitalRead(TRIG_PIN)) if (abortRequested()) { Serial.println(F("# aborted")); return; }
    Serial.println(F("# triggered"));
  }

  Serial.print(F("# scan ")); Serial.print(start); Serial.print(F(" -> ")); Serial.print(stop);
  Serial.print(F(" step ")); Serial.print(step); Serial.print(F(", n_avg ")); Serial.print(nAvg);
  Serial.print(F(", ")); Serial.print(nPts); Serial.print(F(" points, est. "));
  Serial.print(nPts * (17.0 + 20.0 * nAvg) / 1000.0, 0); Serial.println(F(" s"));
  printGain();
  Serial.print(F("# offset ")); Serial.print(offsetV * 1000, 3); Serial.println(F(" mV"));
  Serial.println(F("# I_pA > 0 = positive ions into the cup (PRE_OUT below VREF)"));
  if (AMU_PER_VOLT > 0) {
    Serial.print(F("# mass_amu = V_cmd * ")); Serial.print(QPS_STAGE_GAIN, 2);
    Serial.print(F(" * ")); Serial.println(AMU_PER_VOLT, 3);
  }
  printColumns();

  rdyFault = false;
  uint16_t nOvr = 0, firstOvr = 0, done = 0;
  uint32_t t0 = millis();
  uint16_t code = start;
  for (uint16_t k = 0; k < nPts; k++, code += dir * (int16_t)step) {
    if (abortRequested()) { Serial.println(F("# aborted")); break; }
    Point p = measure(code, nAvg, true);
    printPoint(code, p);
    if (p.ovr && nOvr++ == 0) firstOvr = code;
    done++;
  }
  uint32_t dt = millis() - t0;
  Serial.print(F("# done: ")); Serial.print(done); Serial.print(F(" points in "));
  Serial.print(dt / 1000.0, 1); Serial.print(F(" s = "));
  Serial.print(done ? (float)dt / done : 0, 1); Serial.println(F(" ms/point"));
  if (nOvr) {
    Serial.print(F("# WARNING: ")); Serial.print(nOvr);
    Serial.print(F(" points clipped the ADC (first at code ")); Serial.print(firstOvr);
    Serial.println(F("); use a lower gain"));
  }
  if (rdyFault) Serial.println(F("# WARNING: RDY pulse missing on D2, timing fell back to timeouts"));
}

// ---------------------------------------------------------------- zero
void zero(bool save) {
  Serial.println(F("# zero: beam must be OFF"));
  rdyFault = false;
  Point p = measure(dacCode, ZERO_WINDOWS, false);
  offsetV = p.vDiff;
  Serial.print(F("# offset = ")); Serial.print(offsetV * 1000, 3); Serial.print(F(" mV = "));
  Serial.print(-offsetV / RF_OHM * 1e12, 2); Serial.println(F(" pA (now subtracted)"));
  if (p.ovr) Serial.println(F("# WARNING: preamp clipped, offset is not valid"));
  if (save) {
    EeData e = { EE_MAGIC, offsetV, gainIdx };
    eeprom_update_block(&e, eeSlot, sizeof(e));
    Serial.println(F("# saved to EEPROM (offset + gain)"));
  }
}

// ---------------------------------------------------------------- self-check
bool found(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

void verdict(bool ok) { Serial.println(ok ? F("  PASS") : F("  FAIL")); }

// average of n single-ended/differential conversions, in volts, at a given gain
float readVolts(uint16_t mux, uint8_t gi, uint8_t n) {
  startMux(mux, GAINS[gi]);
  nextConv();
  long s = 0;
  for (uint8_t k = 0; k < n; k++) s += nextConv();
  return (float)s / n * (GAIN_FS[gi] / 32768.0);
}

void selfCheck() {
  bool all = true;
  Serial.println(F("# I2C scan:"));
  for (uint8_t a = 1; a < 127; a++)
    if (found(a)) { Serial.print(F("#   0x")); Serial.println(a, HEX); }

  bool okAds = found(ADS_ADDR), okDac = found(DAC_ADDR);
  Serial.print(F("ADS1115 at 0x48")); verdict(okAds);
  Serial.print(F("MCP4725 at 0x60")); verdict(okDac);
  if (!okDac && (found(0x61) || found(0x62) || found(0x63)))
    Serial.println(F("#   an MCP4725 answers at 0x61-0x63: check its address jumper (need 0x60)"));
  if (!okAds || !okDac) { Serial.println(F("SELF-CHECK: FAIL")); return; }

  // RDY pulses on D2: count them over 200 ms of continuous conversion
  startMux(ADS1X15_REG_CONFIG_MUX_DIFF_1_3, GAINS[gainIdx]);
  nextConv();
  noInterrupts(); rdyCount = 0; uint32_t tA = rdyTime; interrupts();
  delay(200);
  noInterrupts(); uint8_t nr = rdyCount; uint32_t tB = rdyTime; interrupts();
  bool okRdy = nr >= 40 && nr <= 60;                 // 250 SPS +/-10 % -> ~45-55
  Serial.print(F("RDY on D2: ")); Serial.print(nr); Serial.print(F(" pulses in 200 ms"));
  if (nr > 1) {
    float sps = nr / ((tB - tA) / 1e6);
    Serial.print(F(" = ")); Serial.print(sps, 1); Serial.print(F(" SPS, 20 ms window really "));
    Serial.print(SAMPLES_PER_WINDOW * 1000.0 / sps, 2); Serial.print(F(" ms"));
  }
  verdict(okRdy); all &= okRdy;

  // A2 tracks the DAC (through JP1)
  uint16_t keep = dacCode;
  float supply = -1;                                  // 5 V rail seen by the divider, from the DAC full scale
  if (JP1_BRIDGED) {
    const uint16_t C[3] = { 410, 2048, 3686 };
    float v[3];
    for (uint8_t k = 0; k < 3; k++) {
      dac.setVoltage(C[k], false);
      delay(SETTLE_MS);
      v[k] = readVolts(ADS1X15_REG_CONFIG_MUX_SINGLE_2, 0, 4);
    }
    float slope = (v[2] - v[0]) / (C[2] - C[0]);     // V per code
    float off = v[0] - slope * C[0];
    float rail = slope * 4096;
    float mid = v[1] - (off + slope * C[1]);
    bool okTrk = rail > 4.5 && rail < 5.3 && fabs(off) < 0.020 && fabs(mid) < 0.010;
    Serial.print(F("A2 read-back (JP1): "));
    for (uint8_t k = 0; k < 3; k++) { Serial.print(C[k]); Serial.print('='); Serial.print(v[k], 3); Serial.print(F(" V ")); }
    Serial.print(F("-> full scale ")); Serial.print(rail, 3); Serial.print(F(" V, offset "));
    Serial.print(off * 1000, 1); Serial.print(F(" mV, mid error ")); Serial.print(mid * 1000, 1);
    Serial.print(F(" mV"));
    verdict(okTrk); all &= okTrk;
    if (okTrk) supply = rail;
    if (!okTrk && rail < 1.0) Serial.println(F("#   A2 reads ~0: is JP1 bridged? MCP4725 in the right way round?"));
    dac.setVoltage(keep, false);
    delay(SETTLE_MS);
  } else {
    Serial.println(F("A2 read-back: skipped (JP1_BRIDGED = false)"));
  }

  // VREF on A3. VREF = 5V/2 from a divider, so judge it against the real USB rail
  // (measured above as the DAC's full scale on A2), not a fixed window: a 4.7 V
  // laptop port gives 2.35 V, which is correct, not a fault.
  float vref = readVolts(ADS1X15_REG_CONFIG_MUX_SINGLE_3, 0, 8);
  bool okRef;
  Serial.print(F("VREF (A3) = ")); Serial.print(vref, 4);
  if (supply > 0) {
    float want = supply / 2, err = (vref - want) / want;
    okRef = fabs(err) < 0.02;                           // 1 % divider + buffer offset
    Serial.print(F(" V, want ")); Serial.print(want, 3); Serial.print(F(" (rail/2), error "));
    Serial.print(err * 100, 2); Serial.print(F(" %"));
  } else {
    okRef = vref >= 2.25 && vref <= 2.75;               // no rail reading: USB 4.5-5.5 V
    Serial.print(F(" V, want 2.25-2.75 (rail unknown)"));
  }
  verdict(okRef); all &= okRef;

  // preamp not clipped (beam should be off)
  float vd = readVolts(ADS1X15_REG_CONFIG_MUX_DIFF_1_3, 1, 10);
  bool okPre = fabs(vd) < 2.3;
  Serial.print(F("Preamp A1-A3 = ")); Serial.print(vd * 1000, 2); Serial.print(F(" mV = "));
  Serial.print(-vd / RF_OHM * 1e12, 1); Serial.print(F(" pA (raw), not clipped"));
  verdict(okPre); all &= okPre;
  if (okPre && fabs(vd) > 0.1) Serial.println(F("#   note: > 1 nA with no beam? check the input / guard, then 'z'"));

  Serial.print(F("TRIG IN (D8) idle: "));
  Serial.println(digitalRead(TRIG_PIN) ? F("HIGH (expected LOW unless a trigger source is driving it)") : F("LOW ok"));

  Serial.println(all ? F("SELF-CHECK: PASS") : F("SELF-CHECK: FAIL"));
}

// ---------------------------------------------------------------- commands
void help() {
  Serial.println(F("# z [save] | s start stop step [n_avg] | t [start stop step [n_avg]] | r [n_avg] | d code | g 2/3|1|2|4|8|16 | i"));
}

// parse up to 4 unsigned integers after the command letter; returns how many
uint8_t parseArgs(char *s, long *a, uint8_t maxN) {
  uint8_t n = 0;
  char *tok = strtok(s, " ,\t");
  while (tok && n < maxN) { a[n++] = atol(tok); tok = strtok(nullptr, " ,\t"); }
  return n;
}

bool setScanArgs(char *args, bool allowEmpty) {
  long a[4];
  uint8_t n = parseArgs(args, a, 4);
  if (n == 0 && allowEmpty) return true;
  if (n < 3 || a[0] < 0 || a[0] > 4095 || a[1] < 0 || a[1] > 4095 || a[2] < 1 || a[2] > 4095) {
    Serial.println(F("# usage: s <start 0-4095> <stop 0-4095> <step >=1> [n_avg 1-50]"));
    return false;
  }
  long avg = n > 3 ? a[3] : 1;
  if (avg < 1 || avg > 50) { Serial.println(F("# n_avg 1-50")); return false; }
  scanStart = a[0]; scanStop = a[1]; scanStep = a[2]; scanAvg = avg;
  return true;
}

void handle(char *line) {
  while (*line == ' ') line++;
  char cmd = *line;
  char *args = line + 1;
  switch (cmd) {
    case 'z': case 'Z':
      zero(strstr(args, "save") != nullptr);
      break;
    case 's': case 'S':
      if (setScanArgs(args, false)) scan(scanStart, scanStop, scanStep, scanAvg, false);
      break;
    case 't': case 'T':
      if (setScanArgs(args, true)) scan(scanStart, scanStop, scanStep, scanAvg, true);
      break;
    case 'r': case 'R': {
      long a[1]; long n = parseArgs(args, a, 1) ? a[0] : 1;
      if (n < 1 || n > 50) n = 1;
      rdyFault = false;
      printColumns();
      printPoint(dacCode, measure(dacCode, n, false));
      if (rdyFault) Serial.println(F("# WARNING: RDY pulse missing on D2"));
      break;
    }
    case 'd': case 'D': {
      long a[1];
      if (parseArgs(args, a, 1) != 1 || a[0] < 0 || a[0] > 4095) { Serial.println(F("# usage: d <0-4095>")); break; }
      dac.setVoltage(a[0], false); dacCode = a[0];
      Serial.print(F("# DAC = ")); Serial.println(dacCode);
      break;
    }
    case 'g': case 'G': {
      while (*args == ' ') args++;
      uint8_t gi = 255;
      if (strncmp(args, "2/3", 3) == 0 || strncmp(args, "0.6", 3) == 0) gi = 0;
      else switch (atoi(args)) { case 1: gi = 1; break; case 2: gi = 2; break; case 4: gi = 3; break;
                                 case 8: gi = 4; break; case 16: gi = 5; break; }
      if (gi == 255) { Serial.println(F("# usage: g 2/3|1|2|4|8|16")); break; }
      gainIdx = gi;
      printGain();
      Serial.println(F("# re-run 'z' after changing gain"));
      break;
    }
    case 'i': case 'I': selfCheck(); break;
    case 'h': case 'H': case '?': help(); break;
    default: Serial.print(F("# unknown: ")); Serial.println(line); help();
  }
}

// ---------------------------------------------------------------- setup / loop
void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, INPUT);            // R3 pulls it low
  pinMode(RDY_PIN, INPUT);             // breakout pulls it high
  Serial.println(F("\n# === MIE1001 DAQ shield scan ==="));

  Wire.begin();
  if (!ads.begin(ADS_ADDR)) Serial.println(F("# ADS1115 not found at 0x48 (run 'i')"));
  if (!dac.begin(DAC_ADDR)) Serial.println(F("# MCP4725 not found at 0x60 (run 'i')"));
  Wire.setClock(400000);               // after the begin()s, which reset it to 100 kHz
  Wire.setWireTimeout(25000, true);
  ads.setDataRate(RATE_ADS1115_250SPS);
  dac.setVoltage(0, false);            // mass command to 0 V (the chip powers up at mid-scale)
  dacCode = 0;
  attachInterrupt(digitalPinToInterrupt(RDY_PIN), onRdy, FALLING);

  EeData e;
  eeprom_read_block(&e, eeSlot, sizeof(e));
  if (e.magic == EE_MAGIC && e.gainIdx < 6 && fabs(e.offsetV) < 1.0) {
    offsetV = e.offsetV; gainIdx = e.gainIdx;
    Serial.print(F("# offset from EEPROM: ")); Serial.print(offsetV * 1000, 3); Serial.println(F(" mV"));
  }
  printGain();
  help();
}

char buf[40];
uint8_t len = 0;

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      buf[len] = 0;
      if (len) handle(buf);
      len = 0;
    } else if (len < sizeof(buf) - 1) {
      buf[len++] = c;
    }
  }
}
