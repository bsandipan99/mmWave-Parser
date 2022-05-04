import serial
import time
import numpy as np
import matplotlib.pyplot as plt
import fft
import math

# TO DO: Add your own config file
configFileName = 'all_profiles.cfg'
CLIport = {}
Dataport = {}
byteBuffer = np.zeros(2 ** 15, dtype='uint8')
byteBufferLength = 0

NUM_ANGLE_BINS = 64
range_depth = 10
range_width = 5


# ------------------------------------------------------------------

# Function to configure the serial ports and send the data from
# the configuration file to the radar
def serialConfig(configFileName):
    global CLIport
    global Dataport
    # Open the serial ports for the configuration and the data ports

    # Raspberry pi
    CLIport = serial.Serial('/dev/ttyACM1', 115200)
    Dataport = serial.Serial('/dev/ttyACM2', 921600)

    # Windows
    # CLIport = serial.Serial('COM3', 115200)
    # Dataport = serial.Serial('COM4', 921600)

    # Read the configuration file and send it to the board
    config = [line.rstrip('\r\n') for line in open(configFileName)]
    for i in config:
        CLIport.write((i + '\n').encode())
        print(i)
        time.sleep(0.01)

    return CLIport, Dataport


# ------------------------------------------------------------------

# Function to parse the data inside the configuration file
def parseConfigFile(configFileName):
    configParameters = {}  # Initialize an empty dictionary to store the configuration parameters

    # Read the configuration file and send it to the board
    config = [line.rstrip('\r\n') for line in open(configFileName)]
    for i in config:

        # Split the line
        splitWords = i.split(" ")

        # Hard code the number of antennas, change if other configuration is used
        numRxAnt = 4
        numTxAnt = 2

        # Get the information about the profile configuration
        if "profileCfg" in splitWords[0]:
            startFreq = int(float(splitWords[2]))
            idleTime = int(splitWords[3])
            rampEndTime = float(splitWords[5])
            freqSlopeConst = float(splitWords[8])
            numAdcSamples = int(splitWords[10])
            numAdcSamplesRoundTo2 = 1

            while numAdcSamples > numAdcSamplesRoundTo2:
                numAdcSamplesRoundTo2 = numAdcSamplesRoundTo2 * 2

            digOutSampleRate = int(splitWords[11])

        # Get the information about the frame configuration
        elif "frameCfg" in splitWords[0]:

            chirpStartIdx = int(splitWords[1])
            chirpEndIdx = int(splitWords[2])
            numLoops = int(splitWords[3])
            numFrames = int(splitWords[4])
            framePeriodicity = int(splitWords[5])

    # Combine the read data to obtain the configuration parameters
    numChirpsPerFrame = (chirpEndIdx - chirpStartIdx + 1) * numLoops
    configParameters["numDopplerBins"] = numChirpsPerFrame / numTxAnt
    configParameters["numRangeBins"] = numAdcSamplesRoundTo2
    configParameters["rangeResolutionMeters"] = (3e8 * digOutSampleRate * 1e3) / (
            2 * freqSlopeConst * 1e12 * numAdcSamples)
    configParameters["rangeIdxToMeters"] = (3e8 * digOutSampleRate * 1e3) / (
            2 * freqSlopeConst * 1e12 * configParameters["numRangeBins"])
    configParameters["dopplerResolutionMps"] = 3e8 / (
            2 * startFreq * 1e9 * (idleTime + rampEndTime) * 1e-6 * configParameters["numDopplerBins"] * numTxAnt)
    configParameters["maxRange"] = (300 * 0.9 * digOutSampleRate) / (2 * freqSlopeConst * 1e3)
    configParameters["maxVelocity"] = 3e8 / (4 * startFreq * 1e9 * (idleTime + rampEndTime) * 1e-6 * numTxAnt)

    return configParameters


# ------------------------------------------------------------------

# Helper methods for processing

def tensor_f(vec1, vec2):
    t = []
    for r in range(0, len(vec1)):
        t.append(np.multiply(np.array(vec2), vec1[r]))
    return t


def meshgrid(xvec, yvec):
    x = []
    y = []
    for r in range(0, len(yvec)):
        for c in range(0, len(xvec)):
            x.append(xvec[c])
            y.append(yvec[r])
    return [x, y]


def reshape_rowbased(vec, rows, cols):
    t = []
    start = 0
    for r in range(0, rows):
        row = vec[start: start + cols]
        t.append(row)
        start += cols
    return t


# Function to process detected points tlvtype=1

def processDetectedPoints(byteBuffer, idX, configParameters):
    # word array to convert 4 bytes to a 16 bit number
    word = [1, 2 ** 8]
    tlv_numObj = np.matmul(byteBuffer[idX:idX + 2], word)
    idX += 2
    tlv_xyzQFormat = 2 ** np.matmul(byteBuffer[idX:idX + 2], word)
    idX += 2

    # Initialize the arrays
    rangeIdx = np.zeros(tlv_numObj, dtype='int16')
    dopplerIdx = np.zeros(tlv_numObj, dtype='int16')
    peakVal = np.zeros(tlv_numObj, dtype='int16')
    x = np.zeros(tlv_numObj, dtype='int16')
    y = np.zeros(tlv_numObj, dtype='int16')
    z = np.zeros(tlv_numObj, dtype='int16')

    for objectNum in range(tlv_numObj):
        # Read the data for each object
        rangeIdx[objectNum] = np.matmul(byteBuffer[idX:idX + 2], word)
        idX += 2
        dopplerIdx[objectNum] = np.matmul(byteBuffer[idX:idX + 2], word)
        idX += 2
        peakVal[objectNum] = np.matmul(byteBuffer[idX:idX + 2], word)
        idX += 2
        x[objectNum] = np.matmul(byteBuffer[idX:idX + 2], word)
        idX += 2
        y[objectNum] = np.matmul(byteBuffer[idX:idX + 2], word)
        idX += 2
        z[objectNum] = np.matmul(byteBuffer[idX:idX + 2], word)
        idX += 2

    # Make the necessary corrections and calculate the rest of the data
    rangeVal = rangeIdx * configParameters["rangeIdxToMeters"]
    dopplerIdx[dopplerIdx > (configParameters["numDopplerBins"] / 2 - 1)] = dopplerIdx[dopplerIdx > (
            configParameters["numDopplerBins"] / 2 - 1)] - 65535
    dopplerVal = dopplerIdx * configParameters["dopplerResolutionMps"]
    # x[x > 32767] = x[x > 32767] - 65536
    # y[y > 32767] = y[y > 32767] - 65536
    # z[z > 32767] = z[z > 32767] - 65536
    x = x / tlv_xyzQFormat
    y = y / tlv_xyzQFormat
    z = z / tlv_xyzQFormat

    # Store the data in the detObj dictionary
    detObj = {"numObj": tlv_numObj, "rangeIdx": rangeIdx, "range": rangeVal, "dopplerIdx": dopplerIdx,
              "doppler": dopplerVal, "peakVal": peakVal, "x": x, "y": y, "z": z}
    print('detObj', detObj)
    dataOK = 1
    print('idX after detecting points:', idX)
    return detObj


def processRangeNoiseProfile(byteBuffer, idX, detObj, configParameters, isRangeProfile):
    traceidX = 0
    if isRangeProfile:
        traceidX = 0
    else:
        traceidX = 2
    numrp = 2 * configParameters["numRangeBins"]
    rp = byteBuffer[idX:idX + numrp]
    idX += numrp


def processAzimuthHeatMap(byteBuffer, idX, configParameters):
    numTxAnt = 2
    numRxAnt = 4
    numBytes = numRxAnt * numTxAnt * configParameters["numRangeBins"] * 4
    q = byteBuffer[idX:idX + numBytes]
    idX += numBytes
    q_rows = numTxAnt * numRxAnt
    q_cols = configParameters["numRangeBins"]
    q_idx = 0
    QQ = []
    NUM_ANGLE_BINS = 64
    for i in range(0, q_cols):
        real = np.zeros(NUM_ANGLE_BINS)
        img = np.zeros(NUM_ANGLE_BINS)
        for j in range(0, q_rows):
            real[j] = q[q_idx + 1] * 256 + q[q_idx]
            if real[j] > 32767:
                real[j] = real[j] - 65536
            img[j] = q[q_idx + 3] * 256 + q[q_idx + 2]
            if img[j] > 32767:
                img[j] = img[j] - 65536
            q_idx = q_idx + 4
        fft.transform(real, img)
        for ri in range(0, NUM_ANGLE_BINS):
            real[ri] = math.sqrt(real[ri] * real[ri] + img[ri] * img[ri])
        QQ.append([y for x in [real[NUM_ANGLE_BINS / 2:], real[0: NUM_ANGLE_BINS / 2]] for y in x])
    fliplrQQ = []
    for tmpr in range(0, len(QQ)):
        fliplrQQ.append(QQ[tmpr][1:].reverse())
    theta = math.asin(np.multiply(np.arange(-NUM_ANGLE_BINS / 2 + 1, NUM_ANGLE_BINS / 2, 1), 2 / NUM_ANGLE_BINS))
    range = np.multiply(np.arange(0, configParameters["numRangeBins"], 1), configParameters["rangeIdxToMeters"])
    posX = tensor_f(range, math.sin(theta))
    posY = tensor_f(range, math.cos(theta))

    xlin = np.arange(-range_width, range_width, 2 * range_width / 99)
    if len(xlin) < 100:
        xlin = np.append(xlin, range_width)
    ylin = np.arange(0, range_depth, 1.0 * range_depth / 99)
    if len(ylin) < 100:
        ylin = np.append(ylin, range_depth)

    xiyi = meshgrid(xlin, ylin)

    print('posX:', posX, 'posY:', posY, 'xiyi[0]:', xiyi[0], 'xiyi[1]:', xiyi[1])

    zi = fliplrQQ
    zi = reshape_rowbased(zi, len(ylin), len(xlin))
    print('x: ', [xlin], 'y: ', [ylin], 'z: ', [zi])


def processRangeDopplerHeatMap(byteBuffer, idX):
    # Get the number of bytes to read
    numBytes = 2 * configParameters["numRangeBins"] * configParameters["numDopplerBins"]

    # Convert the raw data to int16 array
    payload = byteBuffer[idX:idX + numBytes]
    idX += numBytes
    rangeDoppler = payload.view(dtype=np.int16)

    # Some frames have strange values, skip those frames
    # TO DO: Find why those strange frames happen
    if np.max(rangeDoppler) > 10000:
        return 0

    # Convert the range doppler array to a matrix
    rangeDoppler = np.reshape(rangeDoppler,
                              (configParameters["numDopplerBins"], configParameters["numRangeBins"]),
                              'F')  # Fortran-like reshape
    rangeDoppler = np.append(rangeDoppler[int(len(rangeDoppler) / 2):],
                             rangeDoppler[:int(len(rangeDoppler) / 2)], axis=0)

    # Generate the range and doppler arrays for the plot
    rangeArray = np.array(range(configParameters["numRangeBins"])) * configParameters["rangeIdxToMeters"]
    dopplerArray = np.multiply(
        np.arange(-configParameters["numDopplerBins"] / 2, configParameters["numDopplerBins"] / 2),
        configParameters["dopplerResolutionMps"])

    plt.clf()
    cs = plt.contourf(rangeArray, dopplerArray, rangeDoppler)
    fig.colorbar(cs,
                 shrink=0.9)
    fig.canvas.draw()
    plt.pause(0.1)


def processStatistics(byteBuffer, idX):
    word = [1, 2 ** 8, 2 ** 16, 2 ** 24]
    interFrameProcessingTime = np.matmul(byteBuffer[idX:idX + 4], word)
    idX += 4
    transmitOutputTime = np.matmul(byteBuffer[idX:idX + 4], word)
    idX += 4
    interFrameProcessingMargin = np.matmul(byteBuffer[idX:idX + 4], word)
    idX += 4
    interChirpProcessingMargin = np.matmul(byteBuffer[idX:idX + 4], word)
    idX += 4
    activeFrameCPULoad = np.matmul(byteBuffer[idX:idX + 4], word)
    idX += 4

    interFrameCPULoad = np.matmul(byteBuffer[idX:idX + 4], word)
    idX += 4
    print('Statistical Parameters:',
          ('interFrameProcessingTime: ', interFrameProcessingTime, 'transmitOutputTime: ', transmitOutputTime,
           'interFrameProcessingMargin: ', interFrameProcessingMargin, 'interChirpProcessingMargin: ',
           interChirpProcessingMargin,
           'activeFrameCPULoad: ', activeFrameCPULoad))


def readAndParseData16xx(Dataport, configParameters):
    global byteBuffer, byteBufferLength

    # Constants
    OBJ_STRUCT_SIZE_BYTES = 12
    BYTE_VEC_ACC_MAX_SIZE = 2 ** 15
    MMWDEMO_UART_MSG_DETECTED_POINTS = 1
    MMWDEMO_UART_MSG_RANGE_PROFILE = 2
    MMWDEMO_OUTPUT_MSG_NOISE_PROFILE = 3
    MMWDEMO_OUTPUT_MSG_AZIMUT_STATIC_HEAT_MAP = 4
    MMWDEMO_OUTPUT_MSG_RANGE_DOPPLER_HEAT_MAP = 5
    MMWDEMO_OUTPUT_MSG_STATS = 6
    maxBufferSize = 2 ** 15
    magicWord = [2, 1, 4, 3, 6, 5, 8, 7]

    # Initialize variables
    magicOK = 0  # Checks if magic number has been read
    dataOK = 0  # Checks if the data has been read correctly
    frameNumber = 0
    detObj = {}
    tlv_type = 0

    readBuffer = Dataport.read(Dataport.in_waiting)
    byteVec = np.frombuffer(readBuffer, dtype='uint8')
    byteCount = len(byteVec)

    # Check that the buffer is not full, and then add the data to the buffer
    if (byteBufferLength + byteCount) < maxBufferSize:
        byteBuffer[byteBufferLength:byteBufferLength + byteCount] = byteVec[:byteCount]
        byteBufferLength = byteBufferLength + byteCount

    # Check that the buffer has some data
    if byteBufferLength > 16:

        # Check for all possible locations of the magic word
        possibleLocs = np.where(byteBuffer == magicWord[0])[0]

        # Confirm that is the beginning of the magic word and store the index in startIdx
        startIdx = []
        for loc in possibleLocs:
            check = byteBuffer[loc:loc + 8]
            if np.all(check == magicWord):
                startIdx.append(loc)

        # Check that startIdx is not empty
        if startIdx:

            # Remove the data before the first start index
            if startIdx[0] > 0 and startIdx[0] < byteBufferLength:
                byteBuffer[:byteBufferLength - startIdx[0]] = byteBuffer[startIdx[0]:byteBufferLength]
                byteBuffer[byteBufferLength - startIdx[0]:] = np.zeros(len(byteBuffer[byteBufferLength - startIdx[0]:]),
                                                                       dtype='uint8')
                byteBufferLength = byteBufferLength - startIdx[0]

            # Check that there have no errors with the byte buffer length
            if byteBufferLength < 0:
                byteBufferLength = 0

            # word array to convert 4 bytes to a 32 bit number
            word = [1, 2 ** 8, 2 ** 16, 2 ** 24]

            # Read the total packet length
            totalPacketLen = np.matmul(byteBuffer[12:12 + 4], word)

            # Check that all the packet has been read
            if (byteBufferLength >= totalPacketLen) and (byteBufferLength != 0):
                magicOK = 1

    # If magicOK is equal to 1 then process the message
    if magicOK:
        # word array to convert 4 bytes to a 32 bit number
        word = [1, 2 ** 8, 2 ** 16, 2 ** 24]

        # Initialize the pointer index
        idX = 0

        # Read the header
        magicNumber = byteBuffer[idX:idX + 8]
        idX += 8
        version = format(np.matmul(byteBuffer[idX:idX + 4], word), 'x')
        idX += 4
        totalPacketLen = np.matmul(byteBuffer[idX:idX + 4], word)
        idX += 4
        platform = format(np.matmul(byteBuffer[idX:idX + 4], word), 'x')
        idX += 4
        frameNumber = np.matmul(byteBuffer[idX:idX + 4], word)
        idX += 4
        timeCpuCycles = np.matmul(byteBuffer[idX:idX + 4], word)
        idX += 4
        numDetectedObj = np.matmul(byteBuffer[idX:idX + 4], word)
        idX += 4
        numTLVs = np.matmul(byteBuffer[idX:idX + 4], word)
        idX += 4
        subFrameNumber = np.matmul(byteBuffer[idX:idX + 4], word)
        idX += 4
        print('idx before entering: ', idX)
        # Read the TLV messages
        for tlvIdx in range(numTLVs):

            # word array to convert 4 bytes to a 32 bit number
            word = [1, 2 ** 8, 2 ** 16, 2 ** 24]

            # Check the header of the TLV message
            # try:
            print('Entering after deteing tlv_type = ', tlv_type)
            tlv_type = np.matmul(byteBuffer[idX:idX + 4], word)
            idX += 4
            tlv_length = np.matmul(byteBuffer[idX:idX + 4], word)
            idX += 4
            print('tlv_type', tlv_type)
            print('tlv_length', tlv_length)
            # Read the data depending on the TLV message
            if tlv_type == MMWDEMO_UART_MSG_DETECTED_POINTS:
                detObj = processDetectedPoints(byteBuffer, idX)
            elif tlv_type == MMWDEMO_UART_MSG_RANGE_PROFILE:
                processRangeNoiseProfile(byteBuffer, idX, detObj, isRangeProfile=True)
            elif tlv_type == MMWDEMO_OUTPUT_MSG_NOISE_PROFILE:
                processRangeNoiseProfile(byteBuffer, idX, detObj, isRangeProfile=False)
            elif tlv_type == MMWDEMO_OUTPUT_MSG_AZIMUT_STATIC_HEAT_MAP:
                processAzimuthHeatMap(byteBuffer, idX)
            elif tlv_type == MMWDEMO_OUTPUT_MSG_RANGE_DOPPLER_HEAT_MAP:
                if processStatistics(byteBuffer, idX) == 0:
                    continue
            elif tlv_type == MMWDEMO_OUTPUT_MSG_STATS:
                processStatistics(byteBuffer, idX)

            idX += tlv_length
            print('final idx: ', idX)
            # except Error as e:
            #     print('Here is a pass', e)
            #     pass

        # Remove already processed data
        if idX > 0 and byteBufferLength > idX:
            shiftSize = totalPacketLen

            byteBuffer[:byteBufferLength - shiftSize] = byteBuffer[shiftSize:byteBufferLength]
            byteBuffer[byteBufferLength - shiftSize:] = np.zeros(len(byteBuffer[byteBufferLength - shiftSize:]),
                                                                 dtype='uint8')
            byteBufferLength = byteBufferLength - shiftSize

            # Check that there are no errors with the buffer length
            if byteBufferLength < 0:
                byteBufferLength = 0

    return dataOK, frameNumber, detObj


# -------------------------    MAIN   -----------------------------------------

# Configurate the serial port
CLIport, Dataport = serialConfig(configFileName)

# Get the configuration parameters from the configuration file
configParameters = parseConfigFile(configFileName)

# Main loop
detObj = {}
frameData = {}
currentIndex = 0
fig = plt.figure()
while True:
    try:
        dataOk, frameNumber, detObj = readAndParseData16xx(Dataport, configParameters)
        # print(detObj)
        if dataOk:
            # Store the current frame into frameData
            frameData[currentIndex] = detObj
            currentIndex += 1

        time.sleep(0.03)  # Sampling frequency of 30 Hz

    # Stop the program and close everything if Ctrl + c is pressed
    except KeyboardInterrupt:
        CLIport.write(('sensorStop\n').encode())
        CLIport.close()
        Dataport.close()
        break