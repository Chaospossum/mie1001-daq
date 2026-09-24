// DAQ "mini system" on a breadboard: DAC -> Arduino -> PWM -> ADC
//
//   MCP4725 DAC sets a voltage (the "command")
//     -> UNO A0 reads it (the UNO's own ADC)
//     -> UNO makes a PWM on D9 with the same duty (V / 5 V)
//     -> a 1k + 100 nF (104) RC filter smooths the PWM back into a DC voltage
//     -> ADS1115 A0 measures it
//   If everything works, what the ADS1115 reads equals what the DAC was set to.
//
// Breadboard wiring (UNO + Adafruit ADS1115 + SparkFun MCP4725):
//   UNO 5V   -> ADS1115 VDD, MCP4725 VCC        UNO GND -> ADS1115 GND, MCP4725 GND
//   UNO SDA  -> ADS1115 SDA, MCP4725 SDA        UNO SCL -> ADS1115 SCL, MCP4725 SCL
//   ADS1115 ADDR -> GND (0x48)                  MCP4725 address jumper at 0x60
//   MCP4725 OUT -> UNO A0
//   UNO D9 -> 1k -> ADS1115 A0,   ADS1115 A0 -> 100 nF -> GND
//   optional: MCP4725 OUT -> ADS1115 A1 so the ADS1115 also sees the DAC directly
//
// Libraries: Adafruit ADS1X15, Adafruit MCP4725.  Serial Monitor: 115200 baud, Newline.
// Commands: a voltage (e.g. 2.5) holds the DAC there, 's' runs the sweep again.

#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <Adafruit_MCP4725.h>

Adafruit_ADS1115 ads;
Adafruit_MCP4725 dac;

const uint8_t DAC_ADDR = 0x60;       // NOT the library default (0x62)
const uint8_t CMD_PIN  = A0;         // UNO A0 (not the ADS1115's A0)
const uint8_t PWM_PIN  = 9;          // Timer1 OC1A
const bool    DIRECT_ON_A1 = true;   // set false if MCP4725 OUT is not also wired to ADS1115 A1

// 10-bit PWM on D9 at 15.6 kHz (Timer1, fast PWM, TOP = ICR1 = 1023).
// The 1k + 100 nF filter (1.6 kHz corner) leaves some ripple; the ADS1115 averages each conversion
// over 7.8 ms (~120 PWM periods), so it reads the average voltage.
void pwmBegin() {
  pinMode(PWM_PIN, OUTPUT);
  TCCR1A = _BV(COM1A1) | _BV(WGM11);
  TCCR1B = _BV(WGM13) | _BV(WGM12) | _BV(CS10);
  ICR1 = 1023;
  OCR1A = 0;
}

// The "controller": read the command on UNO A0, copy it to the PWM duty.
// analogRead and the PWM both use the 5 V rail as reference, so its exact value cancels out.
uint16_t cmdCounts = 0;
void follow() {
  long sum = 0;
  for (uint8_t i = 0; i < 8; i++) sum += analogRead(CMD_PIN);
  cmdCounts = sum / 8;
  OCR1A = cmdCounts;
}

float adsVolts(uint8_t ch) {
  ads.readADC_SingleEnded(ch);       // discard one conversion after a channel change
  long sum = 0;
  for (uint8_t i = 0; i < 4; i++) sum += ads.readADC_SingleEnded(ch);
  return ads.computeVolts(sum / 4);
}

void measure(uint16_t code) {
  dac.setVoltage(code, false);
  delay(5);
  follow();
  delay(10);                         // filter settles in ~2.5 ms
  float vOut = adsVolts(0);
  Serial.print(code); Serial.print('\t');
  Serial.print(cmdCounts); Serial.print('\t');
  Serial.print(cmdCounts / 10.23, 1); Serial.print("%\t");
  if (DIRECT_ON_A1) {
    float vIn = adsVolts(1);
    Serial.print(vIn, 3); Serial.print('\t');
    Serial.print(vOut, 3); Serial.print('\t');
    Serial.println((vOut - vIn) * 1000, 0);
  } else {
    Serial.println(vOut, 3);
  }
}

void header() {
  Serial.print(F("\nDAC\tUNO A0\tduty\t"));
  Serial.println(DIRECT_ON_A1 ? F("V_dac\tV_pwm\terr mV") : F("V_pwm"));
}

void sweep() {
  header();
  for (uint16_t code = 0; code <= 4096; code += 512) measure(code > 4095 ? 4095 : code);
}


void setup() {
  Serial.begin(115200);
  Serial.println(F("\n=== DAQ mini chain: DAC -> UNO A0 -> PWM D9 -> ADS1115 ==="));
  Wire.begin();
  Wire.setWireTimeout(25000, true);
  if (!ads.begin(0x48)) { Serial.println(F("ADS1115 not found at 0x48")); while (1); }
  if (!dac.begin(DAC_ADDR)) { Serial.println(F("MCP4725 not found at 0x60")); while (1); }
  ads.setGain(GAIN_TWOTHIRDS);       // +/-6.144 V range
  ads.setDataRate(RATE_ADS1115_128SPS);
  pwmBegin();
  sweep();
  Serial.println(F("\nType a voltage (e.g. 2.5) to hold the DAC there, or 's' to sweep."));
}

void loop() {
  follow();                          // the control loop runs all the time

  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line == "s" || line == "S") { sweep(); return; }
    if (line.length()) {
      float v = line.toFloat();
      if (v < 0 || v > 5.0) { Serial.println(F("0 to 5 V")); return; }
      uint16_t code = min(4095, (int)(v / 5.0 * 4096 + 0.5));  // assumes a 5 V rail; the chain doesn't care
      header();
      measure(code);
    }
  }
}
