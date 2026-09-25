#include "wokwi-api.h"
#include <stdlib.h>
#include <string.h>

#define I2C_ADDRESS 0x60
#define VREF        5.0f

typedef struct {
  pin_t pin_out;
  uint8_t index;
  uint8_t cmd;
  uint16_t value;
  i2c_dev_t i2c_dev;
} chip_state_t;

static void update_output(chip_state_t *chip) {
  float v = (chip->value / 4095.0f) * VREF;
  pin_dac_write(chip->pin_out, v);
}

static bool on_i2c_connect(void *user_data, uint32_t address, bool read) {
  chip_state_t *chip = user_data;
  chip->index = 0;
  return true;
}

static uint8_t on_i2c_read(void *user_data) {
  return 0;
}

static bool on_i2c_write(void *user_data, uint8_t data) {
  chip_state_t *chip = user_data;

  if (chip->index == 0) {
    chip->cmd = data;
    if ((data & 0xC0) == 0x00) {
      chip->value = ((uint16_t)(data & 0x0F)) << 8;
    }
  } else if (chip->index == 1) {
    if ((chip->cmd & 0xC0) == 0x00) {
      chip->value |= data;
      update_output(chip);
    } else {
      chip->value = ((uint16_t)data) << 4;
    }
  } else if (chip->index == 2) {
    chip->value |= (data >> 4);
    update_output(chip);
  }

  chip->index++;
  return true;
}

void chip_init(void) {
  chip_state_t *chip = malloc(sizeof(chip_state_t));
  memset(chip, 0, sizeof(chip_state_t));

  chip->pin_out = pin_init("OUT", ANALOG);
  pin_dac_write(chip->pin_out, 0.0f);

  const i2c_config_t i2c_config = {
    .user_data = chip,
    .address = I2C_ADDRESS,
    .scl = pin_init("SCL", INPUT),
    .sda = pin_init("SDA", INPUT),
    .connect = on_i2c_connect,
    .read = on_i2c_read,
    .write = on_i2c_write,
  };
  chip->i2c_dev = i2c_init(&i2c_config);
}
