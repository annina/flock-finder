/* ----------------------------------------------------------------------
Double-buffering Protomatter example: Continuous concurrent text scrolling 
and eye animation controlled via Pi USB Serial.
------------------------------------------------------------------------- */

#include <Adafruit_Protomatter.h>

#if defined(_VARIANT_MATRIXPORTAL_M4_) // MatrixPortal M4
  uint8_t rgbPins[]  = {7, 8, 9, 10, 11, 12};
  uint8_t addrPins[] = {17, 18, 19, 20, 21};
  uint8_t clockPin   = 14;
  uint8_t latchPin   = 15;
  uint8_t oePin      = 16;
#elif defined(ARDUINO_ADAFRUIT_MATRIXPORTAL_ESP32S3) // MatrixPortal ESP32-S3
  uint8_t rgbPins[]  = {42, 41, 40, 38, 39, 37};
  uint8_t addrPins[] = {45, 36, 48, 35, 21};
  uint8_t clockPin   = 2;
  uint8_t latchPin   = 47;
  uint8_t oePin      = 14;
#elif defined(_VARIANT_FEATHER_M4_) // Feather M4 + RGB Matrix FeatherWing
  uint8_t rgbPins[]  = {6, 5, 9, 11, 10, 12};
  uint8_t addrPins[] = {A5, A4, A3, A2};
  uint8_t clockPin   = 13;
  uint8_t latchPin   = 0;
  uint8_t oePin      = 1;
#elif defined(__SAMD51__) // M4 Metro Variants (Express, AirLift)
  uint8_t rgbPins[]  = {6, 5, 9, 11, 10, 12};
  uint8_t addrPins[] = {A5, A4, A3, A2};
  uint8_t clockPin   = 13;
  uint8_t latchPin   = 0;
  uint8_t oePin      = 1;
#endif

Adafruit_Protomatter matrix(
  32,          // Matrix width in pixels
  6,           // Bit depth
  1, rgbPins,  // # of matrix chains
  4, addrPins, // # of address pins
  clockPin, latchPin, oePin, 
  true);       // Double-buffering enabled

// Define Colors
uint16_t COLOR_BLACK;
uint16_t COLOR_WHITE;
uint16_t COLOR_IRIS;  
uint16_t COLOR_PUPIL; 
uint16_t COLOR_YELLOW;  

// --- Eye Geometry Configuration ---
const int eyeCenterX = 16;
const int eyeCenterY = 22; 
const int eyeRadius  = 9;  
const int pupilRadius = 3;  

// Text variables
char message[] = "ROADSIDE SURVEILLANCE CAMERA NEARBY";
int textX = 32; 
int textWidth;

// Framerate clock variables
unsigned long lastFrameTime = 0;
const int frameDelay = 35; 

// Non-blocking Eye Animation State Variables
int currentPupilX = 16;
int targetPupilX = 16;
int eyeState = 0; 
unsigned long eyePauseTimer = 0;

// State Control tracking variable
bool isAlertActive = false; 

void setup() {
  Serial.begin(9600); // USB Serial initialization

  ProtomatterStatus status = matrix.begin();
  
  COLOR_BLACK  = matrix.color565(0, 0, 0);
  COLOR_WHITE  = matrix.color565(255, 255, 255);
  COLOR_IRIS   = matrix.color565(0, 150, 255); 
  COLOR_PUPIL  = matrix.color565(0, 0, 0);
  COLOR_YELLOW = matrix.color565(255, 200, 0);  
  
  matrix.setTextWrap(false); 
  matrix.setTextSize(1);     
  
  textWidth = strlen(message) * 6;
  
  // Start with a clean dark screen
  matrix.fillScreen(COLOR_BLACK);
  matrix.show();
}

void loop() {
  // Check for incoming control bytes from Raspberry Pi
  while (Serial.available() > 0) {
    char command = Serial.read();
    
    if (command == '1') {
      if (!isAlertActive) {
        isAlertActive = true;
        textX = 32; // Reset the scrolling text to begin from the right side
      }
    } 
    else if (command == '0') {
      if (isAlertActive) {
        isAlertActive = false;
        // Instantly shut down visual display assets
        matrix.fillScreen(COLOR_BLACK);
        matrix.show();
      }
    }
  }

  // Only animate if the Raspberry Pi signals a nearby target camera
  if (isAlertActive) {
    if (millis() - lastFrameTime >= frameDelay) {
      lastFrameTime = millis();

      matrix.fillScreen(COLOR_BLACK);

      // Render Text
      matrix.setTextColor(COLOR_YELLOW);
      matrix.setCursor(textX, 0);
      matrix.print(message);
      
      textX--;
      if (textX < -textWidth) {
        textX = 32; 
      }

      // Render Moving Eye
      updateEyeTracking();
      drawLoweredEye(currentPupilX, eyeCenterY);

      matrix.show();
    }
  }
}

void updateEyeTracking() {
  if (currentPupilX < targetPupilX) currentPupilX++;
  if (currentPupilX > targetPupilX) currentPupilX--;

  if (currentPupilX == targetPupilX) {
    if (eyePauseTimer == 0) {
      eyePauseTimer = millis(); 
    }

    unsigned long pauseDuration = 0;
    if (eyeState == 0 || eyeState == 2 || eyeState == 4) pauseDuration = 800;  
    if (eyeState == 1 || eyeState == 3) pauseDuration = 1000;                  

    if (millis() - eyePauseTimer >= pauseDuration) {
      eyePauseTimer = 0; 
      eyeState++;        
      if (eyeState > 4) eyeState = 0; 

      switch (eyeState) {
        case 0: targetPupilX = 16; break; 
        case 1: targetPupilX = 11; break; 
        case 2: targetPupilX = 16; break; 
        case 3: targetPupilX = 21; break; 
        case 4: targetPupilX = 16; break; 
      }
    }
  }
}

void drawLoweredEye(int pupilX, int pupilY) {
  matrix.fillCircle(eyeCenterX, eyeCenterY, eyeRadius, COLOR_WHITE);
  matrix.fillCircle(pupilX, pupilY, pupilRadius + 1, COLOR_IRIS);
  matrix.fillCircle(pupilX, pupilY, pupilRadius, COLOR_PUPIL);
  matrix.drawPixel(pupilX - 1, pupilY - 1, COLOR_WHITE); 
}