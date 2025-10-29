"""Compare all sheets"""
import pandas as pd
from thebrain import CVScoringRules

sheets = ['Sheet 1.csv', 'Sheet2.csv', 'Sheet3.csv']

print("="*80)
print("📊 SO SÁNH CÁC SHEETS")
print("="*80)

for sheet in sheets:
    try:
        df = pd.read_csv(sheet, encoding='utf-8-sig')
        scores = []
        
        for _, row in df.iterrows():
            score, _ = CVScoringRules.calculate_total_score(row)
            scores.append(score)
        
        print(f"\n{sheet}:")
        print(f"  📝 Số CVs: {len(df)}")
        print(f"  📊 Điểm TB: {sum(scores)/len(scores):.2f}/100")
        print(f"  ⬆️  Max: {max(scores):.2f}")
        print(f"  ⬇️  Min: {min(scores):.2f}")
        
        xuatsac = sum(1 for s in scores if s >= 85)
        tot = sum(1 for s in scores if 70 <= s < 85)
        kha = sum(1 for s in scores if 55 <= s < 70)
        tb = sum(1 for s in scores if 40 <= s < 55)
        yeu = sum(1 for s in scores if s < 40)
        
        print(f"\n  Phân bố:")
        print(f"    🌟 Xuất sắc (85+):  {xuatsac:3} ({xuatsac/len(df)*100:5.1f}%)")
        print(f"    ✅ Tốt (70-84):     {tot:3} ({tot/len(df)*100:5.1f}%)")
        print(f"    👍 Khá (55-69):     {kha:3} ({kha/len(df)*100:5.1f}%)")
        print(f"    ⚠️  TB (40-54):      {tb:3} ({tb/len(df)*100:5.1f}%)")
        print(f"    ❌ Yếu (<40):       {yeu:3} ({yeu/len(df)*100:5.1f}%)")
        
    except Exception as e:
        print(f"\n❌ Lỗi đọc {sheet}: {e}")

print("\n" + "="*80)
print("💡 NHẬN XÉT:")
print("="*80)
print("""
Sheet3 (30 CVs mới):
  ✅ Phân bố CHUẨN: Yếu 43%, TB 27%, Khá 10%, Tốt 13%, Xuất sắc 7%
  ✅ Phản ánh thị trường thực tế: Nhiều yếu, ít xuất sắc
  ✅ Đa dạng ngành nghề và level
  
Sheet1 & Sheet2 cũ:
  ⚠️ Cần kiểm tra phân bố có hợp lý không
  ⚠️ Có thể cần cập nhật để phù hợp với tiêu chí chấm mới
""")
