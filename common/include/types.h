#pragma once
#include <stdint.h>

struct sha256_hash{
    uint8_t bytes[32];
};

typedef struct sha256_hash sha256_hash_t;