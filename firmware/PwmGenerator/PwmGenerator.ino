/*
 * PwmGenerator - a pulse width modulator for Uno / Nano / Pro Mini.
 *
 * Two independent-duty PWM outputs on a shared, freely chosen frequency:
 *
 *     pin 9  = channel A
 *     pin 10 = channel B
 *
 * Drive it over the serial monitor at 115200 baud, 'Newline' line ending:
 *
 *     f 20000     set frequency to 20 kHz (0.25 Hz .. 1 MHz)
 *     a 37.5      channel A duty, in percent
 *     b 90        channel B duty, in percent
 *     ph 90       shift channel B 90 degrees behind channel A
 *     pot on|off  let A0 control channel A's duty instead
 *     sweep       one 0 -> 100 -> 0 % ramp on channel A
 *     s           status
 *     ?           this list
 *
 * Optional hardware: a potentiometer's wiper on A0, an LED + ~220R resistor
 * (or a scope probe) on pin 9. Nothing extra is required to try the commands.
 */

/*
 * Pwm16 - hardware PWM on Timer1 (ATmega328P: Uno, Nano, Pro Mini)
 *
 *   Channel A -> pin 9   (OC1A / PB1)
 *   Channel B -> pin 10  (OC1B / PB2)
 *
 * Two operating modes, switched automatically by pwmSetPhase():
 *
 *   phase == 0  HARDWARE mode. Fast PWM, TOP in ICR1, both pins driven by the
 *               compare units. Jitter-free, works to 1 MHz. A and B are
 *               edge-aligned: they rise together and differ only in duty.
 *
 *   phase != 0  SOFTWARE mode. Timer1 runs in CTC and an ISR steps through the
 *               edge schedule, driving both pins directly. This buys arbitrary
 *               phase between A and B, and costs ISR latency (a few us) and a
 *               much lower usable frequency ceiling. See pwmMaxLatencyUs().
 *
 * Why the mode switch is necessary rather than just clever: in fast PWM the
 * OCR1A/OCR1B registers are double-buffered and only update at BOTTOM, so one
 * compare unit cannot place two independently-timed edges inside one period.
 * Phase-shifting B against A needs four scheduled edges per period, and Timer1
 * has only two compare units - hence the software scheduler.
 *
 * Timer1 is fully occupied either way, so Servo.h cannot be used alongside.
 * millis(), micros() and delay() live on Timer0 and keep working.
 */

#include <Arduino.h>

enum PwmChannel : uint8_t { PWM_A = 0, PWM_B = 1 };

// ===========================================================================
//  Timer1 driver
// ===========================================================================

#if !defined(__AVR_ATmega328P__) && !defined(__AVR_ATmega168__) && !defined(__AVR_ATmega328__)
#warning "Pwm16 targets the ATmega328P (Uno/Nano/Pro Mini). Timer1 registers may differ on this board."
#endif

static const uint8_t PIN_A = 9;    // OC1A / PB1
static const uint8_t PIN_B = 10;   // OC1B / PB2
static const uint8_t BIT_A = _BV(PB1);
static const uint8_t BIT_B = _BV(PB2);

static const uint16_t kPrescalers[] = {1, 8, 64, 256, 1024};
static const uint8_t  kCsBits[]     = {_BV(CS10),
                                       _BV(CS11),
                                       _BV(CS11) | _BV(CS10),
                                       _BV(CS12),
                                       _BV(CS12) | _BV(CS10)};
static const uint8_t  kNumPrescalers = sizeof(kPrescalers) / sizeof(kPrescalers[0]);

// Cost of the scheduler ISR plus interrupt entry, in CPU cycles. Two edges
// closer together than this cannot both be serviced, so the schedule builder
// spreads them apart and raises the "strained" flag.
//
// Counted from the disassembly of __vector_11: ~127 cycles of body (the C ISR
// saves a lot of registers for the 16-bit array indexing) plus ~5 cycles of
// entry latency. 160 leaves headroom; pwmMaxLatencyUs() reports what the chip
// actually measures, so this constant only has to be a safe upper bound.
static const uint16_t kIsrCycles = 160;

static uint16_t sTop        = 0;     // period - 1, in timer counts
static uint16_t sPrescaler  = 1;
static uint8_t  sCsBits     = _BV(CS10);
static float    sActualHz   = 0.0f;
static float    sDuty[2]    = {0.0f, 0.0f};
static float    sPhaseDeg   = 0.0f;
static bool     sRunning    = false;

// --- software scheduler state ---------------------------------------------
static volatile bool     sSoftMode   = false;
static volatile uint8_t  sEvtCount   = 0;
static volatile uint8_t  sEvtIdx     = 0;
static volatile uint16_t sEvtDelta[4];   // counts from previous event to this one
static volatile uint8_t  sEvtSet[4];     // PORTB bits to raise
static volatile uint8_t  sEvtClr[4];     // PORTB bits to drop
static volatile uint16_t sMaxLatency = 0;
static bool              sStrained   = false;

// In CTC the counter is zeroed by the compare match, so TCNT1 read at ISR entry
// is exactly the latency in timer counts. Free, honest instrumentation.
ISR(TIMER1_COMPA_vect) {
  uint16_t lat = TCNT1;

  uint8_t i = sEvtIdx;
  uint8_t p = PORTB;
  p |=  sEvtSet[i];
  p &= ~sEvtClr[i];
  PORTB = p;

  if (++i >= sEvtCount) i = 0;
  sEvtIdx = i;
  OCR1A = sEvtDelta[i] - 1;

  if (lat > sMaxLatency) sMaxLatency = lat;
}

// --- hardware mode ---------------------------------------------------------

static void applyDutyHw(PwmChannel ch) {
  const float   duty = sDuty[ch];
  const uint8_t pin  = (ch == PWM_A) ? PIN_A : PIN_B;
  const uint8_t com  = (ch == PWM_A) ? _BV(COM1A1) : _BV(COM1B1);

  if (duty <= 0.0f) { TCCR1A &= ~com; digitalWrite(pin, LOW);  return; }
  if (duty >= 1.0f) { TCCR1A &= ~com; digitalWrite(pin, HIGH); return; }

  uint32_t counts = (uint32_t)(duty * ((uint32_t)sTop + 1) + 0.5f);
  if (counts == 0)     counts = 1;
  if (counts > sTop)   counts = sTop;

  uint8_t sreg = SREG;
  cli();
  if (ch == PWM_A) OCR1A = (uint16_t)counts;
  else             OCR1B = (uint16_t)counts;
  SREG = sreg;

  TCCR1A |= com;
}

static void startHardwareMode() {
  uint8_t sreg = SREG;
  cli();
  TIMSK1 = 0;                              // no scheduler interrupt
  // WGM13:0 = 1110 -> fast PWM, TOP = ICR1.
  TCCR1A = _BV(WGM11);
  TCCR1B = _BV(WGM13) | _BV(WGM12) | sCsBits;
  ICR1   = sTop;
  TCNT1  = 0;
  SREG = sreg;

  sSoftMode = false;
  applyDutyHw(PWM_A);
  applyDutyHw(PWM_B);
}

// --- software mode ---------------------------------------------------------

// Build the per-period edge schedule. Returns false if the outputs are static
// (no edges needed), in which case the caller holds the pins at fixed levels.
static bool buildSchedule() {
  const uint32_t period = (uint32_t)sTop + 1;

  struct Evt { uint32_t t; uint8_t set; uint8_t clr; };
  Evt e[4];
  uint8_t n = 0;

  uint8_t staticHigh = 0;   // bits held high for the whole period
  uint8_t staticLow  = 0;

  // Channel A is the phase reference: it rises at t = 0.
  if      (sDuty[PWM_A] <= 0.0f) staticLow  |= BIT_A;
  else if (sDuty[PWM_A] >= 1.0f) staticHigh |= BIT_A;
  else {
    uint32_t fall = (uint32_t)(sDuty[PWM_A] * period + 0.5f);
    if (fall == 0)      fall = 1;
    if (fall >= period) fall = period - 1;
    e[n++] = (Evt){0,    BIT_A, 0};
    e[n++] = (Evt){fall, 0,     BIT_A};
  }

  // Channel B rises at the phase offset and falls a duty-width later, wrapping
  // around the period boundary if it has to.
  if      (sDuty[PWM_B] <= 0.0f) staticLow  |= BIT_B;
  else if (sDuty[PWM_B] >= 1.0f) staticHigh |= BIT_B;
  else {
    uint32_t rise  = (uint32_t)((sPhaseDeg / 360.0f) * period + 0.5f) % period;
    uint32_t width = (uint32_t)(sDuty[PWM_B] * period + 0.5f);
    if (width == 0)      width = 1;
    if (width >= period) width = period - 1;
    uint32_t fall = (rise + width) % period;
    e[n++] = (Evt){rise, BIT_B, 0};
    e[n++] = (Evt){fall, 0,     BIT_B};
  }

  // Whatever is static this period gets applied once, here.
  uint8_t p = PORTB;
  p |=  staticHigh;
  p &= ~staticLow;
  PORTB = p;

  if (n == 0) return false;

  // Sort by time (n <= 4, so insertion sort is the right tool).
  for (uint8_t i = 1; i < n; i++) {
    Evt k = e[i];
    int8_t j = i - 1;
    while (j >= 0 && e[j].t > k.t) { e[j + 1] = e[j]; j--; }
    e[j + 1] = k;
  }

  // Merge coincident edges, then enforce a minimum spacing the ISR can service.
  // Both steps can only reduce the event count, never grow it.
  uint8_t m = 0;
  for (uint8_t i = 0; i < n; i++) {
    if (m > 0 && e[i].t == e[m - 1].t) {
      e[m - 1].set |= e[i].set;
      e[m - 1].clr |= e[i].clr;
    } else {
      e[m++] = e[i];
    }
  }
  n = m;

  uint16_t minGap = kIsrCycles / sPrescaler;
  if (minGap < 1) minGap = 1;
  sStrained = false;

  // Push events apart where they crowd. Distorts the waveform, but a missed
  // compare match would cost a whole period, which is far worse.
  for (uint8_t i = 1; i < n; i++) {
    if (e[i].t - e[i - 1].t < minGap) {
      e[i].t = e[i - 1].t + minGap;
      sStrained = true;
    }
  }
  if (n > 1 && (period - e[n - 1].t) < minGap) {
    // The wrap-around gap is too tight as well; drop the last edge's time back.
    e[n - 1].t = period - minGap;
    sStrained = true;
    if (e[n - 1].t <= e[n - 2].t) return false;   // hopeless: give up on edges
  }

  // Convert absolute times to deltas. Event 0's delta is measured from the
  // last event of the previous period, across the boundary.
  uint16_t delta[4];
  for (uint8_t i = 1; i < n; i++) delta[i] = (uint16_t)(e[i].t - e[i - 1].t);
  delta[0] = (uint16_t)(period - e[n - 1].t + e[0].t);
  if (delta[0] == 0) delta[0] = 1;

  uint8_t sreg = SREG;
  cli();
  for (uint8_t i = 0; i < n; i++) {
    sEvtDelta[i] = delta[i];
    sEvtSet[i]   = e[i].set;
    sEvtClr[i]   = e[i].clr;
  }
  sEvtCount = n;
  SREG = sreg;
  return true;
}

static void startSoftwareMode() {
  bool haveEdges = buildSchedule();

  uint8_t sreg = SREG;
  cli();
  TCCR1A = 0;                                   // compare outputs disconnected;
  TCCR1B = _BV(WGM12) | sCsBits;                // WGM = CTC, TOP = OCR1A.
  if (haveEdges) {
    sEvtIdx = 0;
    OCR1A   = sEvtDelta[0] - 1;
    TCNT1   = 0;
    TIFR1   = _BV(OCF1A);                       // clear a stale pending match
    TIMSK1  = _BV(OCIE1A);
  } else {
    TIMSK1 = 0;                                 // static levels, nothing to do
    OCR1A  = sTop;
  }
  SREG = sreg;
  sSoftMode = true;
}

// --- shared ----------------------------------------------------------------

static void applyMode() {
  if (sPhaseDeg == 0.0f) startHardwareMode();
  else                   startSoftwareMode();
}

static float configureTimer(float frequencyHz) {
  if (frequencyHz < 0.25f)      frequencyHz = 0.25f;
  if (frequencyHz > 1000000.0f) frequencyHz = 1000000.0f;

  uint16_t prescaler = kPrescalers[kNumPrescalers - 1];
  uint8_t  csBits    = kCsBits[kNumPrescalers - 1];
  uint32_t top       = 65535;

  for (uint8_t i = 0; i < kNumPrescalers; i++) {
    float candidate = (float)F_CPU / ((float)kPrescalers[i] * frequencyHz) - 1.0f;
    if (candidate <= 65535.0f) {
      prescaler = kPrescalers[i];
      csBits    = kCsBits[i];
      top       = (uint32_t)(candidate + 0.5f);
      break;
    }
  }
  if (top < 1)     top = 1;
  if (top > 65535) top = 65535;

  sTop       = (uint16_t)top;
  sPrescaler = prescaler;
  sCsBits    = csBits;
  sActualHz  = (float)F_CPU / ((float)prescaler * ((float)top + 1.0f));
  return sActualHz;
}

float pwmBegin(float frequencyHz) {
  pinMode(PIN_A, OUTPUT);
  pinMode(PIN_B, OUTPUT);
  digitalWrite(PIN_A, LOW);
  digitalWrite(PIN_B, LOW);

  TCCR1A = 0; TCCR1B = 0; TIMSK1 = 0; TCNT1 = 0;
  sDuty[PWM_A] = 0.0f;
  sDuty[PWM_B] = 0.0f;
  sPhaseDeg    = 0.0f;
  sMaxLatency  = 0;

  float hz = configureTimer(frequencyHz);
  sRunning = true;
  applyMode();
  return hz;
}

float pwmSetFrequency(float frequencyHz) {
  if (!sRunning) return pwmBegin(frequencyHz);
  float hz = configureTimer(frequencyHz);
  sMaxLatency = 0;
  applyMode();          // TOP moved, so every edge time has to be recomputed
  return hz;
}

void pwmSetDuty(PwmChannel ch, float duty) {
  if (duty < 0.0f) duty = 0.0f;
  if (duty > 1.0f) duty = 1.0f;
  sDuty[ch] = duty;
  if (!sRunning) return;
  if (sSoftMode) startSoftwareMode();
  else           applyDutyHw(ch);
}

void pwmSetDutyRaw(PwmChannel ch, uint16_t counts) {
  if (counts > sTop) counts = sTop;
  pwmSetDuty(ch, (float)counts / ((float)sTop + 1.0f));
}

void pwmSetPhase(float degrees) {
  degrees = fmod(degrees, 360.0f);
  if (degrees < 0.0f) degrees += 360.0f;
  sPhaseDeg   = degrees;
  sMaxLatency = 0;
  if (sRunning) applyMode();
}

void pwmEnd() {
  uint8_t sreg = SREG;
  cli();
  TIMSK1 = 0;
  TCCR1A = 0;
  TCCR1B = 0;
  SREG = sreg;
  sRunning  = false;
  sSoftMode = false;
  digitalWrite(PIN_A, LOW);
  digitalWrite(PIN_B, LOW);
}

uint16_t pwmTop()            { return sTop; }
float    pwmFrequency()      { return sActualHz; }
float    pwmResolutionBits() { return log((float)sTop + 1.0f) / log(2.0f); }
float    pwmPhase()          { return sPhaseDeg; }
bool     pwmSoftwareMode()   { return sSoftMode; }
bool     pwmScheduleStrained() { return sSoftMode && sStrained; }
void     pwmResetLatency()   { uint8_t s = SREG; cli(); sMaxLatency = 0; SREG = s; }

float pwmMaxLatencyUs() {
  uint8_t s = SREG; cli();
  uint16_t lat = sMaxLatency;
  SREG = s;
  return (float)lat * (float)sPrescaler / (F_CPU / 1000000.0f);
}

// ===========================================================================
//  Sketch - serial command interface
// ===========================================================================

static const unsigned long kBaud       = 115200;
static const float         kStartHz    = 1000.0f;
static const uint8_t       kPotPin     = A0;
static const uint16_t      kPotDeadband = 4;  // ADC counts of hysteresis

static bool     potMode     = false;
static uint16_t lastPotRaw  = 0;
static char     line[32];
static uint8_t  lineLen     = 0;

// ---------------------------------------------------------------------------

// Duty is shadowed locally so status reports what was asked for, not what the
// compare register rounded to.
static float shadowDuty[2] = {0.0f, 0.0f};

static float dutyPercent(PwmChannel ch) { return shadowDuty[ch] * 100.0f; }

static void setDutyPercent(PwmChannel ch, float percent) {
  if (percent < 0.0f)   percent = 0.0f;
  if (percent > 100.0f) percent = 100.0f;
  shadowDuty[ch] = percent / 100.0f;
  pwmSetDuty(ch, shadowDuty[ch]);
}

static void printStatus() {
  Serial.println(F("--- PWM status ---"));
  Serial.print(F("  frequency : ")); Serial.print(pwmFrequency(), 3); Serial.println(F(" Hz"));
  Serial.print(F("  TOP       : ")); Serial.print(pwmTop());
  Serial.print(F("  ("));            Serial.print(pwmResolutionBits(), 2);
  Serial.println(F(" bits of duty resolution)"));
  Serial.print(F("  A (pin 9) : ")); Serial.print(dutyPercent(PWM_A), 2); Serial.println(F(" %"));
  Serial.print(F("  B (pin 10): ")); Serial.print(dutyPercent(PWM_B), 2); Serial.println(F(" %"));
  Serial.print(F("  phase B-A : ")); Serial.print(pwmPhase(), 1); Serial.println(F(" deg"));
  Serial.print(F("  mode      : "));
  Serial.println(pwmSoftwareMode() ? F("software (ISR scheduler)") : F("hardware (compare units)"));
  if (pwmSoftwareMode()) {
    Serial.print(F("  ISR jitter: worst ")); Serial.print(pwmMaxLatencyUs(), 2);
    Serial.println(F(" us  <- real phase/duty error"));
    if (pwmScheduleStrained())
      Serial.println(F("  WARNING   : edges too close to service - output is being distorted"));
  }
  Serial.print(F("  A0 control: ")); Serial.println(potMode ? F("on") : F("off"));
}

static void printHelp() {
  Serial.println(F("f <hz>      frequency, 0.25 .. 1000000"));
  Serial.println(F("a <pct>     duty on pin 9"));
  Serial.println(F("b <pct>     duty on pin 10"));
  Serial.println(F("ph <deg>    phase of pin 10 behind pin 9, 0 .. 360"));
  Serial.println(F("pot on|off  A0 potentiometer drives channel A"));
  Serial.println(F("sweep       0 -> 100 -> 0 % ramp on channel A"));
  Serial.println(F("s           status"));
}

static void doSweep() {
  Serial.println(F("sweeping channel A..."));
  const bool wasPot = potMode;
  potMode = false;
  for (int p = 0; p <= 100; p++) { setDutyPercent(PWM_A, p); delay(15); }
  for (int p = 100; p >= 0; p--) { setDutyPercent(PWM_A, p); delay(15); }
  potMode = wasPot;
  Serial.println(F("done"));
}

static void handleLine(char *s) {
  while (*s == ' ') s++;
  if (*s == '\0') return;

  const char cmd = *s;
  char *arg = s + 1;
  while (*arg == ' ') arg++;

  switch (cmd) {
    case 'f': {
      float hz = atof(arg);
      float actual = pwmSetFrequency(hz);
      Serial.print(F("frequency -> ")); Serial.print(actual, 3);
      Serial.print(F(" Hz, ")); Serial.print(pwmResolutionBits(), 2);
      Serial.println(F(" bits"));
      break;
    }
    case 'a':
      setDutyPercent(PWM_A, atof(arg));
      Serial.print(F("A -> ")); Serial.print(dutyPercent(PWM_A), 2); Serial.println(F(" %"));
      break;
    case 'b':
      setDutyPercent(PWM_B, atof(arg));
      Serial.print(F("B -> ")); Serial.print(dutyPercent(PWM_B), 2); Serial.println(F(" %"));
      break;
    case 'p':
      if (s[1] == 'h') {                      // "ph <deg>"
        char *deg = s + 2;
        while (*deg == ' ') deg++;
        pwmSetPhase(atof(deg));
        Serial.print(F("phase -> ")); Serial.print(pwmPhase(), 1);
        Serial.print(F(" deg, "));
        Serial.println(pwmSoftwareMode() ? F("software mode") : F("hardware mode"));
        if (pwmScheduleStrained())
          Serial.println(F("WARNING: edges too close to service at this frequency"));
        break;
      }
      // Match against the whole line: `arg` starts mid-word here ("pot off"
      // leaves arg pointing at "ot off"), so a prefix compare would misread it.
      potMode = (strstr(s, "off") == NULL);   // "pot" alone turns it on
      Serial.print(F("A0 control ")); Serial.println(potMode ? F("on") : F("off"));
      break;
    case 'S':
    case 's':
      if (s[1] == 'w') doSweep();   // "sweep"
      else             printStatus();
      break;
    case '?':
    case 'h':
      printHelp();
      break;
    default:
      Serial.println(F("? unknown command - type ? for the list"));
  }
}

// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(kBaud);
  while (!Serial) { ; }   // needed on native-USB boards, harmless on a Uno

  float hz = pwmBegin(kStartHz);
  setDutyPercent(PWM_A, 50.0f);
  setDutyPercent(PWM_B, 25.0f);

  Serial.println(F("\nPWM generator ready - pin 9 = A, pin 10 = B"));
  Serial.print(F("starting at ")); Serial.print(hz, 2); Serial.println(F(" Hz"));
  printHelp();
  lastPotRaw = analogRead(kPotPin);
}

void loop() {
  // Serial command parsing, one character at a time so loop() never blocks.
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[lineLen] = '\0';
      handleLine(line);
      lineLen = 0;
    } else if (lineLen < sizeof(line) - 1) {
      line[lineLen++] = c;
    }
  }

  if (potMode) {
    uint16_t raw = analogRead(kPotPin);
    // Deadband keeps ADC noise from rewriting OCR1A on every pass.
    if ((raw > lastPotRaw ? raw - lastPotRaw : lastPotRaw - raw) >= kPotDeadband) {
      lastPotRaw = raw;
      setDutyPercent(PWM_A, raw * (100.0f / 1023.0f));
    }
  }
}
