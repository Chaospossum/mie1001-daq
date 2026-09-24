// DAQ shield loopback test: MCP4725 DAC -> ADS1115 ADC
//
// Wiring: one wire from QPS OUT (J2, signal terminal) to SIGNAL IN (J1, signal terminal).
// GND is already shared on the board. Nothing else connected to J1/J2.
//
// Libraries (Library Manager): Adafruit ADS1X15, Adafruit MCP4725
// Board: Arduino Uno. Serial Monitor: 115200 baud.
//
// What it does:
//   1. finds both chips on I2C (ADS1115 0x48, MCP4725 0x60)
//   2. sweeps the DAC 0 -> 4095 in 17 steps, reads each step back on ADS1115 A0
//   3. fits a straight line and reports offset, full scale (= the 5 V rail) and worst error
//   4. then waits for commands: type a voltage (e.g. 1.25) to set the DAC and read it back,
//      or 's' to run the sweep again

#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <Adafruit_MCP4725.h>

Adafruit_ADS1115 ads;
Adafruit_MCP4725 dac;

const uint8_t ADS_ADDR = 0x48;
const uint8_t DAC_ADDR = 0x60;   // NOT the library default (0x62)
const uint8_t TRIG_PIN = 8;
const uint8_t ALRT_PIN = 2;

float dacFullScale = 5.0;        // updated by the sweep

float readVolts(uint8_t n = 8) {
  long sum = 0;
  for (uint8_t i = 0; i < n; i++) sum += ads.readADC_SingleEnded(0);
  return ads.computeVolts(sum / n);
}

float setAndRead(uint16_t code) {
  dac.setVoltage(code, false);   // false = don't touch the EEPROM
  delay(10);                     // DAC settles in ~6 us, the 4k7 + 100 nF filter in ~2.5 ms
  readVolts(1);                  // throw away one conversion started before the step
  return readVolts();
}

void sweep() {
  const uint8_t N = 17;
  uint16_t code[N];
  float v[N];

  Serial.println(F("\n  code    V_meas"));
  for (uint8_t i = 0; i < N; i++) {
    code[i] = (i == N - 1) ? 4095 : i * 256;
    v[i] = setAndRead(code[i]);
    Serial.print(F("  ")); Serial.print(code[i]);
    Serial.print(F("\t")); Serial.println(v[i], 4);
  }

  // least-squares line V = a + b*code
  float sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (uint8_t i = 0; i < N; i++) {
    sx += code[i]; sy += v[i];
    sxx += (float)code[i] * code[i]; sxy += (float)code[i] * v[i];
  }
  float b = (N * sxy - sx * sy) / (N * sxx - sx * sx);
  float a = (sy - b * sx) / N;
  dacFullScale = b * 4096.0;

  float worst = 0;
  bool monotonic = true;
  for (uint8_t i = 0; i < N; i++) {
    float err = v[i] - (a + b * code[i]);
    if (fabs(err) > fabs(worst)) worst = err;
    if (i && v[i] <= v[i - 1]) monotonic = false;
  }

  Serial.println();
  Serial.print(F("Offset at code 0:   ")); Serial.print(a * 1000, 1); Serial.println(F(" mV"));
  Serial.print(F("Full scale (= 5V):  ")); Serial.print(dacFullScale, 3); Serial.println(F(" V"));
  Serial.print(F("Worst line error:   ")); Serial.print(worst * 1000, 1); Serial.println(F(" mV"));
  Serial.print(F("Monotonic:          ")); Serial.println(monotonic ? F("yes") : F("NO"));

  bool pass = monotonic && fabs(a) < 0.020 && fabs(worst) < 0.020
              && dacFullScale > 4.5 && dacFullScale < 5.3;
  Serial.println(pass ? F("\nRESULT: PASS") : F("\nRESULT: FAIL  (see notes at the top of the sketch)"));
  if (dacFullScale < 1.0)
    Serial.println(F("  Reading ~0 V everywhere: is the J2 -> J1 wire in? Is the MCP4725 plugged in the right way round?"));

  dac.setVoltage(0, false);
}

bool found(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, INPUT);      // R3 on the board pulls it low
  pinMode(ALRT_PIN, INPUT);      // the ADS1115 breakout pulls it high
  Serial.println(F("\n=== DAQ shield: MCP4725 -> ADS1115 loopback ==="));

  Wire.begin();
  Wire.setWireTimeout(25000, true);

  bool okAds = found(ADS_ADDR), okDac = found(DAC_ADDR);
  Serial.print(F("ADS1115 @0x48: ")); Serial.println(okAds ? F("found") : F("MISSING"));
  Serial.print(F("MCP4725 @0x60: ")); Serial.println(okDac ? F("found") : F("MISSING"));
  if (!okAds || !okDac) {
    Serial.println(F("Scanning the bus:"));
    for (uint8_t a = 1; a < 127; a++)
      if (found(a)) { Serial.print(F("  device at 0x")); Serial.println(a, HEX); }
    Serial.println(F("Fix it and press reset."));
    while (1);
  }

  ads.begin(ADS_ADDR);
  ads.setGain(GAIN_TWOTHIRDS);           // +/-6.144 V range, 0.1875 mV per count
  ads.setDataRate(RATE_ADS1115_128SPS);
  dac.begin(DAC_ADDR);

  Serial.print(F("D8 (TRIG IN) idle: "));
  Serial.println(digitalRead(TRIG_PIN) ? F("HIGH  <-- expected LOW, check R3") : F("LOW ok"));

  sweep();
  Serial.println(F("\nType a voltage (e.g. 2.5) to set the DAC, or 's' to sweep again."));
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  if (line == "s" || line == "S") { sweep(); return; }

  float target = line.toFloat();
  if (target < 0 || target > dacFullScale) {
    Serial.print(F("Range is 0 to ")); Serial.print(dacFullScale, 2); Serial.println(F(" V"));
    return;
  }
  uint16_t code = (uint16_t)(target / dacFullScale * 4096.0 + 0.5);
  if (code > 4095) code = 4095;
  float v = setAndRead(code);
  Serial.print(F("set ")); Serial.print(target, 3);
  Serial.print(F(" V (code ")); Serial.print(code);
  Serial.print(F(")  ->  read ")); Serial.print(v, 4);
  Serial.print(F(" V  (error ")); Serial.print((v - target) * 1000, 1); Serial.println(F(" mV)"));
}
