#include "wokwi-api.h"
#include <stdlib.h>
#include <string.h>

#define I2C_ADDRESS 0x48

#define REG_CONVERSION 0
#define REG_CONFIG     1
#define REG_LO_THRESH  2
#define REG_HI_THRESH  3

typedef struct {
  pin_t ain[4];
  uint16_t conversion;
  uint16_t config;
  uint16_t lo_thresh;
  uint16_t hi_thresh;
  uint8_t pointer;
  uint8_t write_index;
  uint8_t read_index;
  uint16_t write_buf;
  i2c_dev_t i2c_dev;
} chip_state_t;

static const float fullscale[8] = {
  6.144f, 4.096f, 2.048f, 1.024f, 0.512f, 0.256f, 0.256f, 0.256f
};

static void do_conversion(chip_state_t *chip) {
  uint8_t mux = (chip->config >> 12) & 0x07;
  uint8_t pga = (chip->config >> 9) & 0x07;
  float fs = fullscale[pga];
  float v;

  if (mux & 0x04) {
    v = pin_adc_read(chip->ain[mux & 0x03]);
  } else {
    switch (mux) {
      case 0: v = pin_adc_read(chip->ain[0]) - pin_adc_read(chip->ain[1]); break;
      case 1: v = pin_adc_read(chip->ain[0]) - pin_adc_read(chip->ain[3]); break;
      case 2: v = pin_adc_read(chip->ain[1]) - pin_adc_read(chip->ain[3]); break;
      default: v = pin_adc_read(chip->ain[2]) - pin_adc_read(chip->ain[3]); break;
    }
  }

  float code = (v / fs) * 32768.0f;
  if (code > 32767.0f) code = 32767.0f;
  if (code < -32768.0f) code = -32768.0f;

  chip->conversion = (uint16_t)(int16_t)code;
  chip->config |= 0x8000;
}

static uint16_t read_register(chip_state_t *chip) {
  switch (chip->pointer) {
    case REG_CONVERSION: return chip->conversion;
    case REG_CONFIG:     return chip->config;
    case REG_LO_THRESH:  return chip->lo_thresh;
    case REG_HI_THRESH:  return chip->hi_thresh;
    default:             return 0;
  }
}

static bool on_i2c_connect(void *user_data, uint32_t address, bool read) {
  chip_state_t *chip = user_data;
  chip->write_index = 0;
  chip->read_index = 0;
  return true;
}

static uint8_t on_i2c_read(void *user_data) {
  chip_state_t *chip = user_data;
  uint16_t value = read_register(chip);
  uint8_t byte = (chip->read_index == 0) ? (value >> 8) : (value & 0xFF);
  chip->read_index++;
  return byte;
}

static bool on_i2c_write(void *user_data, uint8_t data) {
  chip_state_t *chip = user_data;

  if (chip->write_index == 0) {
    chip->pointer = data & 0x03;
  } else if (chip->write_index == 1) {
    chip->write_buf = ((uint16_t)data) << 8;
  } else if (chip->write_index == 2) {
    chip->write_buf |= data;
    switch (chip->pointer) {
      case REG_CONFIG:
        chip->config = chip->write_buf;
        do_conversion(chip);
        break;
      case REG_LO_THRESH: chip->lo_thresh = chip->write_buf; break;
      case REG_HI_THRESH: chip->hi_thresh = chip->write_buf; break;
    }
  }

  chip->write_index++;
  return true;
}

void chip_init(void) {
  chip_state_t *chip = malloc(sizeof(chip_state_t));
  memset(chip, 0, sizeof(chip_state_t));

  chip->ain[0] = pin_init("A0", ANALOG);
  chip->ain[1] = pin_init("A1", ANALOG);
  chip->ain[2] = pin_init("A2", ANALOG);
  chip->ain[3] = pin_init("A3", ANALOG);

  chip->config = 0x8583;
  chip->lo_thresh = 0x8000;
  chip->hi_thresh = 0x7FFF;

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
