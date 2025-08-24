import pyaudio

def list_audio_devices():
    p = pyaudio.PyAudio()
    print("Available audio devices:")
    print("-" * 50)
    
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        print(f"Device {i}: {info['name']}")
        print(f"  Max input channels: {info['maxInputChannels']}")
        print(f"  Max output channels: {info['maxOutputChannels']}")
        print(f"  Default sample rate: {info['defaultSampleRate']}")
        print()
    
    p.terminate()

if __name__ == "__main__":
    list_audio_devices()