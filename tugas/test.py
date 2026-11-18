import time
import numpy as np
import p3dx



print("Test Program P3DX Hiwonder")

# Connect to the robot
clientID = p3dx.connect()

# Get the sensors handles
sensorsHandle = p3dx.getSensorsHandle(clientID)
# Get the motors handles
motorsHandle = p3dx.getMotorHandle(clientID)


velRobot = [0.0, 0.0]   # [m/s, rad/s]
_velRobot = [0.0, 0.0]  # [m/s, rad/s]

np.set_printoptions(precision=2)

while True:

    k = p3dx.tombol()

    sensorValue = p3dx.getDistance(clientID, sensorsHandle)

    print('\rSensor Values: %s' % (sensorValue), end='', flush=True)



    if k == 'w':
        velRobot = [0.2, 0.0]
    elif k == 's':
        velRobot = [-0.2, 0.0]
    elif k == 'a':
        velRobot = [0.1, 0.2]
    elif k == 'd':
        velRobot = [0.1, -0.2]
    else:
        velRobot = [0.0, 0.0]



    #? Acceleration and deceleration
    _velRobot[0] = 0.1 * velRobot[0] + 0.9 * _velRobot[0]
    _velRobot[1] = 0.1 * velRobot[1] + 0.9 * _velRobot[1]

    # Robot kinematics
    p3dx.robotWheelKine(clientID, motorsHandle, _velRobot)

    #? Press q to quit
    if k == 'q':
        break
    time.sleep(0.01)    





