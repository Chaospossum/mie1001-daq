// ADS1115 self-test — no multimeter needed
// Wiring: VDD->5V  GND->GND  SDA->A4  SCL->A5  ADDR->GND
//         A0->3.3V pin   A1->GND   A2->5V pin   A3->free
// Library: Adafruit ADS1X15 (Tools -> Manage Libraries)

#include <Wire.h>
#include <Adafruit_ADS1X15.h>

Adafruit_ADS1115 ads;
const float LSB = 0.0001875;          // volts per bit at GAIN_TWOTHIRDS (±6.144 V)

// what each channel should read, and how far off is still OK
const char* names[4]    = {"A0 (3.3V pin)", "A1 (GND)", "A2 (5V pin)", "A3 (free)"};
const float expected[4] = {3.30, 0.00, 5.00, -1};   // -1 = don't check
const float tol[4]      = {0.15, 0.03, 0.45, 0};   // 5V pin sags on USB, so wide

void setup() {
  Serial.begin(9600);
  Wire.begin();
  delay(200);
  Serial.println(F("\n=== ADS1115 self-test ==="));

  // 1. Is the chip on the bus?
  Wire.beginTransmission(0x48);
  if (Wire.endTransmission() != 0) {
    Serial.println(F("FAIL: nothing at 0x48. Check SDA/SCL wires, ADDR->GND, VDD->5V."));
    while (1);
  }
  Serial.println(F("OK: ADS1115 found at 0x48"));

  // 2. Start it
  if (!ads.begin(0x48)) {
    Serial.println(F("FAIL: ads.begin() failed"));
    while (1);
  }
  ads.setGain(GAIN_TWOTHIRDS);       // needed to read up to 5 V
  Serial.println(F("OK: ADC initialised\n"));
}

void loop() {
  bool allPass = true;
  for (int ch = 0; ch < 4; ch++) {
    int16_t raw = ads.readADC_SingleEnded(ch);
    float v = raw * LSB;

    Serial.print(names[ch]);
    Serial.print(F("  raw="));
    Serial.print(raw);
    Serial.print(F("  V="));
    Serial.print(v, 3);

    if (expected[ch] >= 0) {
      bool ok = fabs(v - expected[ch]) <= tol[ch];
      Serial.print(ok ? F("   PASS") : F("   FAIL"));
      if (!ok) allPass = false;
    }
    Serial.println();
  }
  Serial.println(allPass ? F("--> all channels PASS\n") : F("--> something is wrong, see FAIL lines\n"));
  delay(2000);
}