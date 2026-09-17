"""Emit the sanitized, explicitly-scoped L2/L3/L6 production payload."""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
raw_dir = Path(r"C:\Users\rulai\Desktop\阿里云")
boss = json.loads((ROOT / "docs/fixtures/flipbelt_ai_snapshot_import.json").read_text(encoding="utf-8"))
boss_rows = []
for row in boss.get("assets", []):
    boss_rows.append({"source_identifier": row.get("ID", "老板台账服务"), "suggested_object_type": "service_instance", "suggested_name": row.get("工具服务") or row.get("平台服务") or row.get("ID", "服务实例"), "confidence": 0.98, "raw_payload": row})
for row in boss.get("dingApps", []):
    boss_rows.append({"source_identifier": row.get("APIID") or row.get("应用名称", "钉钉应用"), "suggested_object_type": "internal_system", "suggested_name": row.get("应用名称") or "钉钉应用", "confidence": 0.98, "raw_payload": row})

mapping = {
    "阿里云.txt": ("阿里云", "阿里云云资源/控制台"), "钉钉.txt": ("钉钉", "钉钉组织与应用"),
    "管易.txt": ("管易", "管易ERP"), "京东旗舰店.txt": ("京东", "京东旗舰店运营"),
    "聚水潭.txt": ("聚水潭", "聚水潭及云仓"), "新浪邮箱.txt": ("新浪邮箱", "新浪邮箱/微博"),
    "影刀.txt": ("影刀", "影刀自动化与VPN"), "用友YS.txt": ("用友云", "用友云"),
    "预策.txt": ("预策", "真理时刻/样板房业务环境"), "知蝉网及平台账号.txt": ("知蝉网", "知产维权访问服务"),
    "知产维权账号密码总 飞比特.txt": ("阿里知识产权保护平台", "知识产权维权与登记服务"),
    "中国物品编码中心.txt": ("中国物品编码中心", "GS1企业服务"), "专利查询.txt": ("专利查询系统", "专利查询服务"),
    "flipbelt邮箱.txt": ("网易企业邮箱", "企业邮箱服务"),
}
aliyun_rows = []
for filename, (platform, service) in mapping.items():
    path = raw_dir / filename
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    identities = list(dict.fromkeys(re.findall(r"[^\s,;，；:：()（）<>]+@[^\s,;，；()（）<>]+|1\d{10}", text)))
    aliyun_rows.append({"source_identifier": filename, "suggested_object_type": "resource", "suggested_name": service, "confidence": 0.9, "raw_payload": {"平台": platform, "工具服务": service, "来源文件": filename}})
    for index, identity in enumerate(identities, 1):
        aliyun_rows.append({"source_identifier": f"{filename}#身份{index}", "suggested_object_type": "registration_identity", "suggested_name": identity, "confidence": 0.92, "raw_payload": {"平台": platform, "注册身份": identity, "来源文件": filename}})

print(json.dumps({"batches": [
    {"file_name": "老板台账静态快照（服务与钉钉应用）", "source_kind": "boss_ledger_curated", "records": boss_rows},
    {"file_name": "阿里云目录（逐文件必要事实）", "source_kind": "aliyun_directory_curated", "records": aliyun_rows},
]}, ensure_ascii=False))
