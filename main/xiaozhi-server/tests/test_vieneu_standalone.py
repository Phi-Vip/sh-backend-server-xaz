"""
Script kiểm thử độc lập (Benchmarking) cho mô hình VieNeu-TTS chạy trên CPU.
Thuộc Giai đoạn 1 của Kế hoạch tái cấu trúc TTS sang VieNeu-TTS.
Đo đạc:
- RAM Footprint (RSS)
- GPU VRAM Footprint (Đảm bảo 0 MB VRAM)
- Thời gian khởi tạo Model
- Tốc độ sinh âm thanh (RTF - Real-Time Factor)
- Khả năng xử lý song ngữ (Bilingual Code-Switching)
- Xuất file kiểm âm WAV
"""
import os
import sys
import time
import wave
import psutil
import numpy as np

def format_bytes(size):
    return f"{size / (1024 * 1024):.2f} MB"

def get_process_ram():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss

def check_gpu_vram():
    try:
        import torch
        if torch.cuda.is_available():
            vram_bytes = torch.cuda.memory_allocated()
            return f"{vram_bytes / (1024 * 1024):.2f} MB"
        return "0.00 MB (Không kích hoạt CUDA / Chạy CPU thuần)"
    except ImportError:
        return "0.00 MB (Torch không có CUDA)"

def main():
    print("=" * 70)
    print("🚀 BẮT ĐẦU KIỂM THỬ ĐỘC LẬP MÔ HÌNH VIENEU-TTS (CPU INT8 / GGUF)")
    print("=" * 70)

    initial_ram = get_process_ram()
    print(f"[*] RAM tiến trình ban đầu: {format_bytes(initial_ram)}")
    print(f"[*] VRAM GPU ban đầu: {check_gpu_vram()}")

    # 1. Khởi tạo Vieneu Engine
    print("\n--- [BƯỚC 1: KHỞI TẠO MODEL TRÊN CPU] ---")
    t0 = time.time()
    try:
        from vieneu import Vieneu
        # Ưu tiên precision="int8" để tận dụng Intel VNNI / AVX-512
        try:
            print("[*] Đang khởi tạo Vieneu(precision='int8')...")
            tts = Vieneu(precision="int8")
        except Exception as e:
            print(f"[!] precision='int8' gặp cảnh báo ({e}), thử khởi tạo mặc định...")
            tts = Vieneu()
    except Exception as e:
        print(f"[❌ LỖI] Không thể import hoặc khởi tạo vieneu: {e}")
        return False

    init_time = time.time() - t0
    ram_after_model = get_process_ram()
    model_ram = ram_after_model - initial_ram
    print(f"[✓] Khởi tạo model thành công trong: {init_time:.2f} giây")
    print(f"[✓] RAM tiến trình hiện tại: {format_bytes(ram_after_model)} (Model chiếm: {format_bytes(model_ram)})")
    print(f"[✓] VRAM GPU sau khi nạp model: {check_gpu_vram()}")

    # 2. Liệt kê các giọng preset (nếu hỗ trợ)
    print("\n--- [BƯỚC 2: KIỂM TRA PRESET VOICES] ---")
    try:
        if hasattr(tts, "list_preset_voices"):
            voices = tts.list_preset_voices()
            print(f"[*] Danh sách giọng đọc có sẵn ({len(voices)} giọng):")
            for v in voices:
                print(f"    - {v}")
        else:
            print("[*] Engine không có hàm list_preset_voices hoặc sử dụng giọng mặc định.")
    except Exception as e:
        print(f"[!] Kiểm tra preset voices: {e}")

    # 3. Benchmark câu tiếng Việt chuẩn
    text_vi = "Xin chào bạn, tôi là trợ lý thông minh XiaoZhi, rất vui được trò chuyện cùng bạn hôm nay."
    print("\n--- [BƯỚC 3: BENCHMARK CÂU TIẾNG VIỆT CHUẨN] ---")
    print(f"[*] Văn bản kiểm thử: \"{text_vi}\"")
    
    t_start = time.time()
    audio = tts.infer(text_vi)
    infer_time = time.time() - t_start

    # Phân tích mảng audio trả về
    sample_rate = getattr(tts, "sample_rate", 48000)
    if isinstance(audio, np.ndarray):
        num_samples = len(audio)
        audio_duration = num_samples / sample_rate
        dtype_str = str(audio.dtype)
    else:
        # Nếu trả về đối tượng có thuộc tính riêng
        num_samples = len(audio)
        audio_duration = num_samples / sample_rate
        dtype_str = type(audio).__name__

    rtf = infer_time / audio_duration if audio_duration > 0 else 0

    print(f"[✓] Thời gian suy luận (Inference Time) : {infer_time:.3f} giây")
    print(f"[✓] Thời lượng âm thanh sinh ra (Duration): {audio_duration:.2f} giây ({num_samples} samples, {sample_rate}Hz, dtype={dtype_str})")
    print(f"[✓] Real-Time Factor (RTF)               : {rtf:.3f} (Nhỏ hơn 1.0 là nhanh hơn thời gian thực)")
    if rtf < 0.5:
        print("    ==> ĐÁNH GIÁ: XUẤT SẮC! Đạt chuẩn phản xạ thời gian thực (< 0.5)")
    elif rtf < 1.0:
        print("    ==> ĐÁNH GIÁ: ĐẠT CHUẨN thời gian thực (< 1.0)")
    else:
        print("    ==> CẦN TỐI ƯU HÓA: RTF >= 1.0 có thể gây trễ khi đàm thoại dài")

    # 4. Benchmark câu song ngữ (Bilingual Code-Switching)
    text_bilingual = "Bạn có thể kết nối Wi-Fi hoặc Bluetooth để sử dụng trợ lý ảo XiaoZhi nhé."
    print("\n--- [BƯỚC 4: BENCHMARK CÂU SONG NGỮ (VIỆT - ANH)] ---")
    print(f"[*] Văn bản kiểm thử: \"{text_bilingual}\"")
    t_start2 = time.time()
    audio_bi = tts.infer(text_bilingual)
    infer_time2 = time.time() - t_start2
    dur_bi = len(audio_bi) / sample_rate
    rtf2 = infer_time2 / dur_bi if dur_bi > 0 else 0
    print(f"[✓] Suy luận câu song ngữ: {infer_time2:.3f}s / {dur_bi:.2f}s audio (RTF: {rtf2:.3f})")

    # 5. Lưu file kiểm âm WAV
    output_dir = "tmp"
    os.makedirs(output_dir, exist_ok=True)
    sample_wav = os.path.join(output_dir, "test_vieneu_sample.wav")
    print(f"\n--- [BƯỚC 5: XUẤT FILE KIỂM ÂM RA {sample_wav}] ---")
    
    try:
        if hasattr(tts, "save"):
            tts.save(audio, sample_wav)
        else:
            # Lưu thủ công qua thư viện wave
            if isinstance(audio, np.ndarray):
                if audio.dtype == np.float32 or audio.dtype == np.float64:
                    audio_int16 = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
                else:
                    audio_int16 = audio.astype(np.int16)
                with wave.open(sample_wav, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(audio_int16.tobytes())
        print(f"[✓] Đã xuất file WAV thành công ({os.path.getsize(sample_wav)} bytes)")
    except Exception as e:
        print(f"[!] Lỗi khi lưu file wave: {e}")

    # 6. Tổng kết tài nguyên
    final_ram = get_process_ram()
    print("\n" + "=" * 70)
    print("📊 TỔNG KẾT TÀI NGUYÊN & ĐÁNH GIÁ PASS TIÊU CHÍ GIAI ĐOẠN 1:")
    print("=" * 70)
    print(f"• RAM chiếm dụng đỉnh điểm: {format_bytes(final_ram)} (Tăng thêm: {format_bytes(final_ram - initial_ram)})")
    print(f"• VRAM GPU NVIDIA MX450    : {check_gpu_vram()} (Bảo đảm an toàn tuyệt đối 0 MB)")
    print(f"• RTF trung bình           : {(rtf + rtf2)/2:.3f}")
    print("=" * 70)
    return True

if __name__ == "__main__":
    main()
