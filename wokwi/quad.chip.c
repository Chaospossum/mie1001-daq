#include "wokwi-api.h"
#include <stdlib.h>
#include <math.h>

#define VIN_MAX     5.0f
#define MZ_MIN      0.0f
#define MZ_MAX      2000.0f

#define PEG_REPEAT  44.0f
#define PEG_OFFSET  41.0f
#define PEG_NMIN    10
#define PEG_NMAX    35
#define PEG_CENTRE  22.0f
#define PEG_SPREAD  5.0f

#define PEAK_SIGMA  0.6f
#define GAIN        2.0f
#define BASELINE    0.02f
#define NOISE       0.008f

typedef struct {
  pin_t pin_in;
  pin_t pin_out;
} chip_state_t;

static float intensity_at(float mz) {
  float signal = 0.0f;

  for (int n = PEG_NMIN; n <= PEG_NMAX; n++) {
    float centre = PEG_REPEAT * n + PEG_OFFSET;
    float d = (mz - centre) / PEAK_SIGMA;
    if (d > 6.0f || d < -6.0f) continue;

    float e = (n - PEG_CENTRE) / PEG_SPREAD;
    float envelope = expf(-0.5f * e * e);

    signal += envelope * expf(-0.5f * d * d);
  }

  return signal;
}

static void chip_timer_event(void *user_data) {
  chip_state_t *chip = (chip_state_t*)user_data;

  float vin = pin_adc_read(chip->pin_in);
  if (vin < 0.0f) vin = 0.0f;
  if (vin > VIN_MAX) vin = VIN_MAX;

  float mz = MZ_MIN + (vin / VIN_MAX) * (MZ_MAX - MZ_MIN);

  float v = BASELINE + GAIN * intensity_at(mz);
  v += ((float)rand() / RAND_MAX - 0.5f) * NOISE;

  if (v < 0.0f) v = 0.0f;
  if (v > 4.0f) v = 4.0f;

  pin_dac_write(chip->pin_out, v);
}

void chip_init(void) {
  chip_state_t *chip = malloc(sizeof(chip_state_t));
  chip->pin_in  = pin_init("IN", ANALOG);
  chip->pin_out = pin_init("OUT", ANALOG);

  const timer_config_t cfg = {
    .callback = chip_timer_event,
    .user_data = chip,
  };
  timer_start(timer_init(&cfg), 200, true);
}
