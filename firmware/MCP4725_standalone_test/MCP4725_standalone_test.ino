// MCP4725 DAC test — stand-alone, uses the Arduino's own ADC on A0
// Wiring: VDD->5V  GND->GND  SDA->A4  SCL->A5  VOUT->A0
// No library needed.

#include <Wire.h>

uint8_t dacAddr = 0;

void setDAC(uint16_t value) {          // 0..4095
  Wire.beginTransmission(dacAddr);
  Wire.write(0x40);                     // write DAC register
  Wire.write(value >> 4);
  Wire.write((value & 0x0F) << 4);
  Wire.endTransmission();
}

int readA0() {                          // average 16 samples, 0..1023
  long sum = 0;
  for (int i = 0; i < 16; i++) sum += analogRead(A0);
  return sum / 16;
}

void setup() {
  Serial.begin(9600);
  delay(200);
  Serial.println(F("\n=== MCP4725 stand-alone test ==="));

  // check the bus lines before touching I2C: both must be pulled HIGH when idle
  pinMode(A4, INPUT); pinMode(A5, INPUT);
  bool sdaHigh = digitalRead(A4), sclHigh = digitalRead(A5);
  Serial.print(F("SDA (A4) idle: ")); Serial.println(sdaHigh ? F("HIGH ok") : F("LOW  <-- stuck! wire to GND or wrong pin"));
  Serial.print(F("SCL (A5) idle: ")); Serial.println(sclHigh ? F("HIGH ok") : F("LOW  <-- stuck! wire to GND or wrong pin"));
  if (!sdaHigh || !sclHigh) { Serial.println(F("Fix the wiring, then press reset.")); while (1); }

  Wire.begin();
  Wire.setWireTimeout(25000, true);   // never hang: give up after 25 ms and reset the bus

  for (uint8_t a = 0x60; a <= 0x63; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) { dacAddr = a; break; }
  }
  if (!dacAddr) {
    Serial.println(F("FAIL: no MCP4725 on 0x60-0x63."));
    Serial.print(F("Scanning whole bus... found: "));
    int n = 0;
    for (uint8_t a = 0x08; a <= 0x77; a++) {
      Wire.beginTransmission(a);
      if (Wire.endTransmission() == 0) { Serial.print(F("0x")); Serial.print(a, HEX); Serial.print(' '); n++; }
    }
    if (!n) Serial.print(F("nothing"));
    Serial.println();
    Serial.println(F("Nothing at all + lines HIGH  -> SDA/SCL swapped, or breakout SDA/SCL pins not in the same rows as the wires."));
    Serial.println(F("Something at another address -> that's probably it; tell me the address."));
    while (1);
  }
  Serial.print(F("OK: MCP4725 found at 0x")); Serial.println(dacAddr, HEX);
  Serial.println();
}

void loop() {
  const uint16_t codes[] = {0, 512, 1024, 2048, 3072, 3584, 4095};
  bool allPass = true;

  for (uint8_t i = 0; i < 7; i++) {
    setDAC(codes[i]);
    delay(20);
    int got      = readA0();
    int expected = (long)codes[i] * 1023 / 4095;      // same 5 V ref on both, so pure ratio
    bool ok = abs(got - expected) <= 12;              // about 60 mV
    if (!ok) allPass = false;

    Serial.print(F("DAC=")); Serial.print(codes[i]);
    Serial.print(F("  expect A0=")); Serial.print(expected);
    Serial.print(F("  got A0=")); Serial.print(got);
    Serial.print(F("  (~")); Serial.print(got * 5.0 / 1023.0, 2); Serial.print(F(" V)"));
    Serial.println(ok ? F("   PASS") : F("   FAIL"));
  }
  Serial.println(allPass ? F("--> DAC PASS\n") : F("--> DAC FAIL, see above\n"));
  setDAC(0);
  delay(3000);
}
