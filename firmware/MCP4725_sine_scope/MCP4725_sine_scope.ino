// MCP4725 sine wave + Arduino as oscilloscope
// Wiring (SparkFun BOB-12918): VCC->5V  GND->GND  SDA->A4  SCL->A5  OUT->A0
// Open Tools -> Serial Plotter at 115200 baud. Two traces: "sent" and "read".

#include <Wire.h>
#define MCP4725_ADDR 0x60          // SparkFun default (A0 jumper to GND)

const int N = 64;                  // samples per sine cycle
int sine[N];

void setDAC(uint16_t v) {
  Wire.beginTransmission(MCP4725_ADDR);
  Wire.write(64);                  // update DAC register
  Wire.write(v >> 4);
  Wire.write((v & 15) << 4);
  Wire.endTransmission();
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  Wire.setClock(400000);           // fast I2C so the wave is smoother
  Wire.setWireTimeout(25000, true);

  // build one cycle, 0..4095 centred on 2048
  for (int i = 0; i < N; i++)
    sine[i] = 2048 + (int)(2047.0 * sin(2 * PI * i / N));

  // is the DAC there?
  Wire.beginTransmission(MCP4725_ADDR);
  if (Wire.endTransmission() != 0) {
    Serial.println(F("MCP4725 not found at 0x60 - check wiring"));
    while (1);
  }
  Serial.println(F("sent,read"));  // trace names for the plotter
}

void loop() {
  static int i = 0;
  setDAC(sine[i]);
  int read = analogRead(A0);       // 0..1023, same 5 V reference as the DAC

  Serial.print(sine[i] / 4);       // scale 12-bit to 10-bit so both traces match
  Serial.print(',');
  Serial.println(read);

  i = (i + 1) % N;
  delay(2);                        // ~7 Hz sine; lower = faster, raise = slower
}
