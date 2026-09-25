// Shared by Ioannis (team 5), shared 24 Sept 2026 -- holds the MCP4725 (0x60) at 3 V.
//
// Change (Nicole, 25 Sept): the MCP4725 uses its own supply as reference, so
// "4095 = 5 V" only holds on an exact 5.00 V rail. On USB the rail is 4.75-5.25 V,
// which made the original code give ~2.9 V. The sketch now measures the rail with the
// ATmega's internal 1.1 V bandgap and computes the code for 3 V from that.
// The bandgap is only +/-10 % from chip to chip: measure the 5V pin once with a
// multimeter, compare with the "rail" value printed, and adjust BANDGAP_MV.
// Ioannis's original line is kept below as a comment.
#include <Wire.h>
#include <Adafruit_MCP4725.h>

Adafruit_MCP4725 dac;

const float TARGET_V = 3.0;
const long BANDGAP_MV = 1100;          // calibrate: BANDGAP_MV * (multimeter 5V / printed rail)

// AVcc in volts, measured against the internal 1.1 V bandgap
float readRail() {
  ADMUX = _BV(REFS0) | _BV(MUX3) | _BV(MUX2) | _BV(MUX1);   // ref = AVcc, input = bandgap
  delay(2);                                                // let the reference settle
  long sum = 0;
  for (uint8_t k = 0; k < 16; k++) {
    ADCSRA |= _BV(ADSC);
    while (ADCSRA & _BV(ADSC)) {}
    if (k >= 8) sum += ADC;                                  // skip the first 8 readings
  }
  return BANDGAP_MV * 1023.0 / (sum / 8.0) / 1000.0;
}

void setup() {
  Serial.begin(115200);
  dac.begin(0x60);

  // 12-bit DAC: 0–4095 corresponds to 0 V to the supply (nominally 5 V)
  // original: 3 V = 3/5 × 4095 ≈ 2457
  // dac.setVoltage(2457, false);
  float rail = readRail();
  uint16_t code = constrain((long)(TARGET_V / rail * 4095 + 0.5), 0, 4095);
  dac.setVoltage(code, false);

  Serial.print(F("rail ")); Serial.print(rail, 3);
  Serial.print(F(" V -> code ")); Serial.print(code);
  Serial.print(F(" -> ")); Serial.print(code * rail / 4095, 3); Serial.println(F(" V"));
}

void loop() {
  // Keep output at 3 V
}
