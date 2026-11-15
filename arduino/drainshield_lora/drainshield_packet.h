// drainshield_packet.h - the radio packet format shared by the node and the receiver
// (and decoded in Python by lora_bridge.py: keep the three in sync).
//
// WHY BINARY, NOT TEXT: LoRa airtime (= battery and radio fairness) grows with every byte.
// One reading as text ("812.4,811.9,-0.3,4,3.92") is ~25 bytes; here it is 13. In the LoRaWAN
// pilot the smallest US915 payload is 11 bytes, so the same thinking carries over.
//
// All fields are little-endian (the ESP32 is little-endian; Python uses struct '<').
#pragma once
#include <stdint.h>

#define DS_MAGIC_UP    0xD5   // node -> receiver
#define DS_MAGIC_ACK   0xA5   // receiver -> node
#define DS_VERSION     1
#define DS_MAX_RECORDS 8      // readings per packet (backlog is sent 8 at a time)

enum DsMode : uint8_t { MODE_DRY = 0, MODE_WATCH = 1, MODE_STORM = 2 };

// Per-reading flags
#define REC_NO_ECHO    0x01   // no valid echo at all this reading
#define REC_AT_BLIND   0x02   // water at (or above) the sensor: sustained blind-zone reading, or echo lost right
                              // after the water was close -> treat as HIGH / FLOODING, never as a false echo
#define REC_SUSPECT    0x04   // reading rejected by the tracking gate (probably a false echo)
#define REC_ICED       0x08   // no echo while the board is below 0 C: probably frost on the sensor face
                              // -> a SENSOR state (grey), never an infrastructure alarm
#define REC_CLOCK_GAP  0x10   // first reading after a power loss: time since the previous reading is unknown
#define REC_ON_USB     0x20   // powered by USB (battery value meaningless)

#pragma pack(push, 1)
struct DsHeader {             // 12 bytes
  uint8_t  magic;             // DS_MAGIC_UP
  uint8_t  version;           // DS_VERSION
  uint16_t node_id;           // which sensor (LoRaWAN would use the DevEUI instead)
  uint32_t first_index;       // running number of the first reading in this packet: the receiver/bridge use it
                              // to drop duplicates when an ACK was lost and the node sends the same readings again
  uint8_t  mode;              // mode the node is in now (DsMode)
  uint8_t  n_records;         // readings that follow (1..DS_MAX_RECORDS)
  uint16_t backlog;           // readings still waiting on the node after this packet
};

struct DsRecord {             // 13 bytes
  uint32_t age_s;             // seconds between the reading and the moment the packet left the node.
                              // The bridge rebuilds the time as (reception time - age): the node needs no
                              // real-time clock, only a clock that keeps counting during deep sleep.
  uint16_t raw_mm;            // median of the pings (0 = no echo)
  uint16_t filt_mm;           // after the tracking loop
  int16_t  rise_mm_min_x10;   // water rise rate x10 (+ = rising), e.g. 25 = +2.5 mm/min
  int8_t   temp_c;            // board temperature (C), rounded
  uint8_t  batt_20mv;         // battery voltage / 20 mV (0..5.1 V)
  uint8_t  flags;             // REC_*
};

struct DsAck {                // 8 bytes
  uint8_t  magic;             // DS_MAGIC_ACK
  uint8_t  version;
  uint16_t node_id;
  uint32_t ack_index;         // = first_index + n_records of the packet being acknowledged
  // (the receiver sends the wanted mode right after, see DsAckMode)
};

struct DsAckMode {            // 10 bytes = DsAck + mode + reserved
  DsAck    ack;
  uint8_t  mode;              // mode the dashboard wants for this node (DsMode)
  uint8_t  reserved;          // 0 (room for a future command)
};
#pragma pack(pop)

static_assert(sizeof(DsHeader) == 12, "header must be 12 bytes");
static_assert(sizeof(DsRecord) == 13, "record must be 13 bytes");
static_assert(sizeof(DsAckMode) == 10, "ack must be 10 bytes");
