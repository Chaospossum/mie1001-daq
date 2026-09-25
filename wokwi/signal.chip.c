#include "wokwi-api.h"
#include <stdlib.h>
#include <math.h>

#define NPOINTS 1000
#define NPEAKS  5

static const float peak_pos[NPEAKS] = {150, 320, 480, 610, 800};
static const float peak_amp[NPEAKS] = {0.8f, 2.4f, 1.5f, 0.6f, 1.1f};
static const float peak_w = 12.0f;
static const float baseline = 0.05f;

typedef struct {
  pin_t pin_out;
  uint32_t step;
} chip_state_t;

static void chip_timer_event(void *user_data) {
  chip_state_t *chip = (chip_state_t*)user_data;
  float x = (float)chip->step;
  float v = baseline;

  for (int i = 0; i < NPEAKS; i++) {
    float d = (x - peak_pos[i]) / peak_w;
    v += peak_amp[i] * expf(-0.5f * d * d);
  }

  v += ((float)rand() / RAND_MAX - 0.5f) * 0.01f;

  if (v < 0.0f) v = 0.0f;
  if (v > 3.0f) v = 3.0f;

  pin_dac_write(chip->pin_out, v);

  chip->step = (chip->step + 1) % NPOINTS;
}

void chip_init(void) {
  chip_state_t *chip = malloc(sizeof(chip_state_t));
  chip->pin_out = pin_init("OUT", ANALOG);
  chip->step = 0;

  const timer_config_t cfg = {
    .callback = chip_timer_event,
    .user_data = chip,
  };
  timer_start(timer_init(&cfg), 1000, true);
}