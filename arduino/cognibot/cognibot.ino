/*
  Cognibot - Arduino UNO firmware (execution layer)

  Receives one-line commands from the laptop over the HC-05 Bluetooth module
  (hardware Serial, pins D0/D1, 9600 baud) and drives the 4 DC motors.

  Commands (end with newline):
    F<cm>    drive forward  <cm> centimetres      e.g. F100
    B<cm>    drive backward <cm> centimetres
    L<deg>   spin left  <deg> degrees             e.g. L90
    R<deg>   spin right <deg> degrees
    S        stop immediately
    P        ping -> replies "PONG <front distance cm>"

  Replies (one line each):
    OK        command accepted, motion started
    DONE      motion finished normally
    BLOCKED n obstacle n cm ahead, motors stopped by the hardware safeguard
    STOPPED   motion cancelled by S
    ERR       unknown / malformed command

  Wiring (from the wire connect table):
    ENA D5, ENB D6, N1 D7, N2 D8, N3 D9, N4 D11
    Ultrasonic  Trig A5, Echo A4        Servo (SG90) D3
    HC-05       TXD->D0(RX)  RXD->D1(TX)

  !! D0/D1 are shared with USB. Unplug the Bluetooth module (or flip the
  !! shield's UART switch) while uploading this sketch.
*/

#include <Servo.h>

// ---------------------------------------------------------------- pins
const uint8_t PIN_ENA = 5;   // motor driver PWM, one side
const uint8_t PIN_ENB = 6;   // motor driver PWM, other side
const uint8_t PIN_N1  = 7;
const uint8_t PIN_N2  = 8;
const uint8_t PIN_N3  = 9;
const uint8_t PIN_N4  = 11;
const uint8_t PIN_TRIG  = A5;
const uint8_t PIN_ECHO  = A4;
const uint8_t PIN_SERVO = 3;

// ------------------------------------------------- tuning / calibration
// Without encoders, distance and angle are TIME based. Measure and adjust:
//   Easiest: run  python calibrate.py  (stop the server first). It sends two
//   test distances and two test angles, asks what you measured, and prints
//   the rate AND offset constants below. Rough manual way:
//   1. send F100, measure real distance d  -> CM_PER_SEC = CM_PER_SEC * d / 100
//   2. send R90,  measure real angle a     -> DEG_PER_SEC = DEG_PER_SEC * a / 90
const uint8_t DRIVE_SPEED = 170;      // PWM 0-255 for straight driving
const uint8_t TURN_SPEED  = 170;      // PWM 0-255 for spinning
float CM_PER_SEC  = 76.500;             // measured at DRIVE_SPEED
float DEG_PER_SEC = 160.000;            // measured at TURN_SPEED

// Real motion = rate * time + offset (start-up lag makes it shorter, coasting
// makes it longer). Run calibrate.py - it measures both and prints these.
//   time = (requested - OFFSET) / RATE
float MOVE_OFFSET_CM  = -42.500;          // extra cm travelled beyond rate*time
float TURN_OFFSET_DEG = -30.000;          // extra degrees turned beyond rate*time

// After every motion: brake, then wait for the car to stop rocking, BEFORE
// replying DONE. Without this, chained turns add up the previous coast.
const unsigned int BRAKE_MS  = 120;
const unsigned int SETTLE_MS = 300;

// If a side spins the wrong way, flip its flag.
const bool INVERT_SIDE_A = true;      // N1/N2 (ENA) motors
const bool INVERT_SIDE_B = false;     // N3/N4 (ENB) motors
// If L/R turn the wrong way (swapped sides), set this to true.
const bool SWAP_TURN = true;

// Hardware safety (independent of anything the LLM asked for)
const int  STOP_DISTANCE_CM = 15;     // stop if something is closer than this
const unsigned long CHECK_EVERY_MS = 60;
const int  MAX_CM  = 500;             // hard clamp, mirrors server limit
const int  MAX_DEG = 180;

// ------------------------------------------------------------- state
Servo head;

enum Mode { IDLE, FORWARD, BACKWARD, TURN_LEFT, TURN_RIGHT };
Mode mode = IDLE;
unsigned long motionEnd = 0;
unsigned long lastCheck = 0;

char lineBuf[16];
uint8_t lineLen = 0;

// ------------------------------------------------------------ motors
void side(uint8_t in1, uint8_t in2, uint8_t en, int dir, uint8_t pwm, bool invert) {
  if (invert) dir = -dir;
  if (dir == 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
    analogWrite(en, 0);
    return;
  }
  digitalWrite(in1, dir > 0 ? HIGH : LOW);
  digitalWrite(in2, dir > 0 ? LOW : HIGH);
  analogWrite(en, pwm);
}

// a, b: +1 forward, -1 backward, 0 stop
void drive(int a, int b, uint8_t pwm) {
  side(PIN_N1, PIN_N2, PIN_ENA, a, pwm, INVERT_SIDE_A);
  side(PIN_N3, PIN_N4, PIN_ENB, b, pwm, INVERT_SIDE_B);
}

void stopMotors() {
  drive(0, 0, 0);
  mode = IDLE;
}

// Active brake (both inputs low + enable high shorts the motor terminals),
// then let the chassis settle so the next command starts from rest.
void brakeAndSettle() {
  digitalWrite(PIN_N1, LOW);
  digitalWrite(PIN_N2, LOW);
  digitalWrite(PIN_N3, LOW);
  digitalWrite(PIN_N4, LOW);
  analogWrite(PIN_ENA, 255);
  analogWrite(PIN_ENB, 255);
  delay(BRAKE_MS);
  drive(0, 0, 0);
  delay(SETTLE_MS);
  mode = IDLE;
}

// -------------------------------------------------------- ultrasonic
// Returns distance in cm, or 999 if no echo (nothing in range).
int readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(3);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 25000UL);  // ~4 m max
  if (us == 0) return 999;
  return (int)(us * 0.0343f / 2.0f);
}

// ---------------------------------------------------------- commands
void startMotion(Mode m, long amount) {
  if (m == FORWARD || m == BACKWARD) {
    amount = constrain(amount, 1, MAX_CM);
    if (m == FORWARD) {
      int d = readDistanceCm();
      if (d < STOP_DISTANCE_CM) {
        Serial.print(F("BLOCKED "));
        Serial.println(d);
        return;
      }
    }
    int dir = (m == FORWARD) ? 1 : -1;
    drive(dir, dir, DRIVE_SPEED);
    float cm = max(0.0f, amount - MOVE_OFFSET_CM);
    motionEnd = millis() + (unsigned long)(cm / CM_PER_SEC * 1000.0f);
  } else {
    amount = constrain(amount, 1, MAX_DEG);
    bool left = (m == TURN_LEFT);
    if (SWAP_TURN) left = !left;
    // spin in place: left side backward + right side forward = turn left
    drive(left ? -1 : 1, left ? 1 : -1, TURN_SPEED);
    float deg = max(0.0f, amount - TURN_OFFSET_DEG);
    motionEnd = millis() + (unsigned long)(deg / DEG_PER_SEC * 1000.0f);
  }
  mode = m;
  lastCheck = millis();
  Serial.println(F("OK"));
}

void handleLine(const char *s) {
  char c = s[0];
  long n = atol(s + 1);

  switch (c) {
    case 'F': case 'f': stopMotors(); startMotion(FORWARD,   n); break;
    case 'B': case 'b': stopMotors(); startMotion(BACKWARD,  n); break;
    case 'L': case 'l': stopMotors(); startMotion(TURN_LEFT, n); break;
    case 'R': case 'r': stopMotors(); startMotion(TURN_RIGHT,n); break;
    case 'S': case 's':
      if (mode != IDLE) { brakeAndSettle(); Serial.println(F("STOPPED")); }
      else Serial.println(F("DONE"));
      break;
    case 'P': case 'p':
      Serial.print(F("PONG "));
      Serial.println(readDistanceCm());
      break;
    default:
      Serial.println(F("ERR"));
  }
}

void readSerial() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      lineBuf[lineLen] = '\0';
      if (lineLen > 0) handleLine(lineBuf);
      lineLen = 0;
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = ch;
    } else {
      lineLen = 0;  // overflow: drop the line
      Serial.println(F("ERR"));
    }
  }
}

// ------------------------------------------------------------ setup
void setup() {
  pinMode(PIN_ENA, OUTPUT);
  pinMode(PIN_ENB, OUTPUT);
  pinMode(PIN_N1, OUTPUT);
  pinMode(PIN_N2, OUTPUT);
  pinMode(PIN_N3, OUTPUT);
  pinMode(PIN_N4, OUTPUT);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  stopMotors();

  head.attach(PIN_SERVO);
  head.write(90);               // ultrasonic sensor looks straight ahead

  Serial.begin(9600);           // HC-05 default data baud rate
}

// ------------------------------------------------------------- loop
void loop() {
  readSerial();

  if (mode == IDLE) return;

  unsigned long now = millis();

  // hardware obstacle safeguard while driving forward
  if (mode == FORWARD && now - lastCheck >= CHECK_EVERY_MS) {
    lastCheck = now;
    int d = readDistanceCm();
    if (d < STOP_DISTANCE_CM) {
      brakeAndSettle();
      Serial.print(F("BLOCKED "));
      Serial.println(d);
      return;
    }
  }

  if ((long)(now - motionEnd) >= 0) {
    brakeAndSettle();
    Serial.println(F("DONE"));
  }
}
