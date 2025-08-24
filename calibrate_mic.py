import pyaudio
import numpy as np
import time

# Audio settings
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024

p = pyaudio.PyAudio()

# List available devices
print("Available input devices:")
for i in range(p.get_device_count()):
    dev = p.get_device_info_by_index(i)
    if dev['maxInputChannels'] > 0:
        print(f"{i}: {dev['name']}")

# Select device
device_index = int(input("\nEnter device index to calibrate: "))

# Open stream
stream = p.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                input_device_index=device_index)

print("\nCalibrating... (speak normally for 5 seconds)")
silent_rms = []
speaking_rms = []

# Measure silence
print("Measuring background noise... (stay silent)")
for _ in range(50):  # 3 seconds
    data = stream.read(CHUNK)
    audio_data = np.frombuffer(data, dtype=np.int16)
    rms = np.sqrt(np.mean(np.square(audio_data.astype(np.float32))))
    silent_rms.append(rms)
    print(f"Silent RMS: {rms:.2f}", end='\r')

# Measure speech
print("\n\nMeasuring speech volume... (speak normally)")
for _ in range(50):  # 3 seconds
    data = stream.read(CHUNK)
    audio_data = np.frombuffer(data, dtype=np.int16)
    rms = np.sqrt(np.mean(np.square(audio_data.astype(np.float32))))
    speaking_rms.append(rms)
    print(f"Speaking RMS: {rms:.2f}", end='\r')

# Calculate averages
avg_silent = sum(silent_rms) / len(silent_rms)
avg_speaking = sum(speaking_rms) / len(speaking_rms)

print("\n\nCalibration results:")
print(f"Average silent RMS: {avg_silent:.2f}")
print(f"Average speaking RMS: {avg_speaking:.2f}")
print(f"Recommended VAD_THRESHOLD: {avg_silent * 1.5:.2f}")

stream.stop_stream()
stream.close()
p.terminate()