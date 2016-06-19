// Likely User Modified Variables ******************************

unsigned long deltaT = 1000; // time between samples (usecs) 1000->50000

float scaleAng = 90/float(238); // Sensor adc->arm angle (degrees)
                                // Be sure to check!

// End Likely User Modified Variables***************************

// For arduino and host interface, SHOULD NOT NEED TO MODIFY!
int angleSensorPin = A0;
int motorVoltagePin = A1;
int motorOutputPin = 9;  // Do not change this!!
int dacMax = 255; // Arduino dac is eight bits.
int adcCenter = 512; //Arduino is 10 bits, 1024/2 = 512
unsigned long transferDt = 50000; // usecs between host updates

// Control variables (set by host).
int direct; // Direct motor command from host.
float desired;  // Desired value (speed or angle) from host.
float Kp, Kd, Ki;  // Feedback gains (proportional, deriv, integral) 

// Variables to reset every time loop restarts.
int loop_counter;
int numSkip;  // Number of loops to skip between host updates.
String inputString = ""; //holds received serial data.
boolean stringComplete; // String received flag.


// Setup sets up pwm frequency (30khz), initializes past values.
void setup() {
  // Set up PWM motor output pin, affects delay() function
  // Delay argument will be in 1/64 milliseconds.
  pinMode(motorOutputPin,OUTPUT);
  digitalWrite(motorOutputPin,LOW);
  setPwmFrequency(motorOutputPin, 1); // Set pwm to approx 30khz.

  // Set for fastest serial transfer.
  Serial.begin(115200);

  // Initialization for data transfer from host.
  inputString.reserve(10);  // Reserve space for rcvd data   
  stringComplete = false;
  numSkip = max(int(transferDt/deltaT),1);  // Number of loops between host transfers.
  loop_counter = 0;  // Initialize counter for status transfer

  // Initialize inputs from host.
  initInputs();

  // Initialize timeSync
  timeSyncInit();
}


// Main code, runs repeatedly
void loop() {  
  // Make sure loop start is deltaT microsecs since last start
  int headroom = timeSync(deltaT);

  // User modifiable code between stars!!
  /***********************************************/
  
  // Read motor arm angle and motor speed.
  float angle = (analogRead(angleSensorPin) - adcCenter)*scaleAng;

  // Compute and scale output motor command
  // NOTE: sign flip to undo pnp transistor driver sign flip
  int motorCmd = direct;
  motorCmd = min(max(motorCmd, 0), dacMax);
  analogWrite(motorOutputPin,dacMax - motorCmd);
  
  /***********************************************/
  
  //check for new parameter values!
  serialEvent();  
  if(stringComplete) processString();

  // Transfer to host occasionally
  if (loop_counter % numSkip == 0) {
    loop_counter = 0;
    printStatus(angle,0,0,0,0,0,headroom);
  }

  // Increment the loop counter.
  loop_counter++;
  
}

// YOU SHOULD NOT NEED TO MODIFY ANY CODE BELOW THIS LINE!!!!!!!!!
// Creates a signed byte number from val, without using 0 and 255
byte signedByte(int val) {
  return byte(min(max(val+128,1),254));
}

char buf[12];  // Twelve bytes to hold data for host.
// Packs up a 10-byte status package for host.
void printStatus(int angle, int error, int deriv, int integral, int mSpd, int mCmd, int hdrm) {
    
  // Start Byte.
  buf[0] = byte(0);
  
  // Write angle and error as signed byte -127 -> 127
  buf[1] = signedByte(angle);
  buf[2] = signedByte(error);
  
  // Write Speed and motor commmand as unsigned 0->253.
  buf[3] = signedByte(mSpd-127);
  buf[4] = signedByte(mCmd-127);

  // Write integral and derivative as two-byte words
  int top = deriv/128;
  deriv -= 128*top;
  buf[5] = signedByte(top);
  buf[6] = signedByte(deriv);
  
  top = integral/128;
  integral -= 128*top;
  buf[7] = signedByte(top);
  buf[8] = signedByte(integral);

  // Write headroom as two byte word.
  top = hdrm/128;
  hdrm -= 128*top;
  buf[9] = signedByte(top);
  buf[10] = signedByte(hdrm);

  // Stop byte (255 otherwise unused).
  buf[11] = byte(255); 

  // Write the buffer to the host.
  Serial.write(buf, 12);
}

void initInputs() {
  // Initial values for variables set from host.
  desired = 0;
  Kp = 0;
  Kd = 0;
  Ki = 0;
  direct = 0;//direct term in motor command
}

void serialEvent() {
  while (Serial.available()) {
    // get the new byte:
    char inChar = (char)Serial.read();
    // add it to the inputString:
    inputString += inChar;
    // if the incoming character is a newline, set a flag
    // so the main loop can do something about it:
    if (inChar == '\n') {
      stringComplete = true;
      break;
    }
  }
}


void processString() {
char St = inputString.charAt(0);
  inputString.remove(0,1);
  float val = inputString.toFloat();
  switch (St) {
    case 'P': 
      Kp = val;
      break;
    case 'I':
      Ki = val;
      break;  
    case 'D':
      Kd = val;
      break;  
    case 'O':  
      direct = val;
      break;
    case 'A':  
      desired = val;
      break;
    default:
    break;  
  }
  inputString = "";
  stringComplete = false;
}


void setPwmFrequency(int pin, int divisor) {
  byte mode;
  if(pin == 5 || pin == 6 || pin == 9 || pin == 10) {
    switch(divisor) {
      case 1: mode = 0x01; break;
      case 8: mode = 0x02; break;
      case 64: mode = 0x03; break;
      case 256: mode = 0x04; break;
      case 1024: mode = 0x05; break;
      default: return;
    }
    if(pin == 5 || pin == 6) {
      TCCR0B = TCCR0B & 0b11111000 | mode;
    } else {
        TCCR1B = TCCR1B & 0b11111000 | mode;
    }
  } else if(pin == 3 || pin == 11) {
    switch(divisor) {
      case 1: mode = 0x01; break;
      case 8: mode = 0x02; break;
      case 32: mode = 0x03; break;
      case 64: mode = 0x04; break;
      case 128: mode = 0x05; break;
      case 256: mode = 0x06; break;
      case 1024: mode = 0x7; break;
      default: return;
    }
    TCCR2B = TCCR2B & 0b11111000 | mode;
  }
}

unsigned long starttime;
int headroom_ts;
boolean switchFlag;
unsigned long scaleT = 1;
int monitorPin = 8;  // for checking time sync

void timeSyncInit() {
  // Frequency Monitor
  pinMode(monitorPin, OUTPUT);
  digitalWrite(monitorPin,LOW);
  if (motorOutputPin == 5 || motorOutputPin == 6) {
    scaleT = 64;
  } else {
    scaleT = 1;
  }
  headroom_ts = 1000;
  starttime = micros();
  switchFlag = true;
}


// Wait until it has been deltaT since this was last called.
// Returns headroom, delay in units of 5us.
int timeSync(unsigned long dT) {
 
  unsigned long delayMuS = max((dT - (micros()-starttime))/scaleT, 1);
 
  if (delayMuS > 5000) {
    delay(delayMuS / 1000); 
    delayMicroseconds(delayMuS % 1000);
  } else {
    delayMicroseconds(delayMuS); // Wait to start exactly deltaT after last start
  }

  headroom_ts = min(headroom_ts,delayMuS);  // min loop headroom should be > 0!!
  starttime = micros(); // Note time loop begins
    
  // Output square wave on monitor pin
  digitalWrite(monitorPin, switchFlag);
  switchFlag = !switchFlag;

  return headroom_ts;
}
