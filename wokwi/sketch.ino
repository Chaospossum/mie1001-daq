#include <Wire.h>
#include <Adafruit_ADS1X15.h>

#define MCP4725_ADDR 0x60

#define SCAN_START   400
#define SCAN_STOP    3000
#define SCAN_STEP    1
#define DWELL_MS     3
#define AVERAGES     2

Adafruit_ADS1115 ads;

void setDAC(uint16_t value) {
  if (value > 4095) value = 4095;
  Wire.beginTransmission(MCP4725_ADDR);
  Wire.write(0x40);
  Wire.write(value >> 4);
  Wire.write((value & 0x0F) << 4);
  Wire.endTransmission();
}

int32_t readAveraged(uint8_t n) {
  int32_t sum = 0;
  for (uint8_t i = 0; i < n; i++) sum += ads.readADC_SingleEnded(0);
  return sum / n;
}

void setup() {
  Serial.begin(9600);
  Wire.begin();

  if (!ads.begin(0x48)) {
    Serial.println("ADS1115 not found.");
    while (1) delay(10);
  }
  ads.setGain(GAIN_ONE);

  setDAC(0);
  delay(100);

  Serial.println("dac,counts");

  for (uint16_t d = SCAN_START; d <= SCAN_STOP; d += SCAN_STEP) {
    setDAC(d);
    delay(DWELL_MS);
    Serial.print(d);
    Serial.print(",");
    Serial.println(readAveraged(AVERAGES));
  }

  Serial.println("scan complete");
  setDAC(0);
}

void loop() {
}