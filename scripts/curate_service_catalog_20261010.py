"""One-time sourced catalog maintenance. Preview/digest first; never infer purchases."""

import argparse
import copy
import json
from uuid import UUID

from app.core.access import get_access_context
from app.db.session import SessionLocal
from app.models import (
    AuditLog,
    Platform,
    Provider,
    ServiceInstance,
    ServiceProduct,
    User,
)
from app.services import catalog_cleanup
from app.services.catalog_reference import REFERENCES
from app.services.service_catalog import digest, directory_record, provider_record
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text


def service(name, plans=(), billing="other"):
    return dict(
        code=digest({"service": name})[:20],
        name=name,
        aliases={name: None},
        plans=list(plans),
        billing=billing,
    )


def reference(code, name, aliases, website, source, services=(), extra_sources=(), note=""):
    return dict(
        code=code,
        name=name,
        aliases=(name, *aliases),
        website=website,
        source=source,
        category="other",
        services=services,
        extra_sources=extra_sources,
        note=note or "官网核对名称与服务入口；未见统一公开套餐，实际套餐须按合同补充。",
    )


def references():
    rows = copy.deepcopy(REFERENCES)
    api = {
        "openai": (
            "OpenAI API",
            "https://developers.openai.com/api/docs/pricing",
            ("按量计费",),
        ),
        "anthropic": (
            "Claude API",
            "https://platform.claude.com/docs/en/about-claude/pricing",
            ("按量计费",),
        ),
        "google": (
            "Gemini API",
            "https://ai.google.dev/gemini-api/docs/pricing",
            ("Free", "Paid", "Enterprise"),
        ),
        "xai": ("Grok API", "https://docs.x.ai/developers/models", ("按量计费",)),
    }
    for row in rows:
        if row["code"] in api:
            name, source, plans = api[row["code"]]
            row["services"] += (service(name, plans, "usage"),)
            row["extra_sources"] = (*row.get("extra_sources", ()), source)
        if row["code"] == "openai":
            row["extra_sources"] += (
                "https://help.openai.com/en/articles/8542115-chatgpt-business-general-faq",
            )
        if row["code"] == "minimax":
            row["aliases"] += ("MinMax",)
        row["note"] = (
            "官方套餐核对于2026-10-10；会员与API分别登记，历史Team保留。审核仅针对目录事实，不推定采购、付款或账号权利。"
        )
    extra = (
        reference(
            "12315",
            "12315",
            (),
            "https://www.12315.cn/",
            "https://www.samr.gov.cn/wljys/sjdt/art/2023/art_b3139687c63c4352b474d616c8a37ac6.html",
            (service("12315维权服务"),),
        ),
        reference(
            "trademark",
            "中国商标网",
            (),
            "https://sbj.cnipa.gov.cn/",
            "https://www.cnipa.gov.cn/",
            (service("中国商标网服务"),),
        ),
        reference(
            "gs1",
            "中国物品编码中心（GS1）",
            ("中国物品编码中心",),
            "https://bizhall.ancc.org.cn/",
            "https://bizhall.ancc.org.cn/",
            (service("中国物品编码中心GS1服务"),),
            note="官方业务大厅及服务主体已核对。旧大厅公告说明入口迁移；实际办理与续展规格按合同登记，不推定固定会员档位。",
        ),
        reference(
            "jd",
            "京东",
            ("京东知识产权保护中心",),
            "https://shop.jd.com/",
            "https://vc.jd.com/",
            tuple(
                service(x)
                for x in (
                    "京东VC服务",
                    "京东企业购服务",
                    "京东店铺运营服务",
                    "京东知识产权维权服务",
                )
            ),
            (
                "https://help.jd.com/user/issue/973-4257.html",
                "https://ir.jd.com/static-files/99686c72-ffeb-4d82-82b2-cbbe80184104",
            ),
            note="京东服务合并到同一目录，服务用途保持分开。VC官方入口已升级到shop.jd.com；采购、商家与维权服务没有统一的Plus/Pro套餐，按实际合同补充。",
        ),
        reference(
            "xiaohongshu",
            "小红书",
            (),
            "https://ipp.xiaohongshu.com/",
            "https://ipp.xiaohongshu.com/",
            (service("小红书知识产权维权服务"),),
        ),
        reference(
            "yingdao",
            "影刀",
            (),
            "https://www.yingdao.com/",
            "https://www.yingdao.com/buy",
            (
                service("影刀服务", ("社区版", "创业版", "企业版"), "subscription"),
                service("影刀助手服务"),
            ),
            ("https://www.yingdao.com/product/",),
            note="公开版本为社区版、创业版、企业版；社区版有非商用范围限制。历史影刀助手名称保留，未推定为某一固定版本；目录审核不代表公司商用批准。",
        ),
        reference(
            "sina-mail",
            "新浪邮箱",
            (),
            "https://mail.sina.com.cn/",
            "https://mail.sina.com.cn/?vt=0",
            (service("新浪邮箱服务", ("免费邮箱", "VIP邮箱"), "subscription"),),
        ),
        reference(
            "sohu-mail",
            "搜狐邮箱",
            (),
            "https://mail.sohu.com/",
            "https://m.mail.sohu.com/app-web1/register.html",
            (service("搜狐邮箱服务"),),
        ),
        reference(
            "zhichan",
            "知蝉网",
            ("知蝉",),
            "https://www.izhichan.com/",
            "https://www.izhichan.com/about",
            (service("知蝉知识产权服务"),),
            ("https://www.izhichan.com/terms/privacy",),
        ),
        reference(
            "guanyi",
            "管易云",
            ("管易", "管易ERP"),
            "https://www.guanyiyun.com/",
            "https://www.kingdee.com/cn",
            (service("管易ERP服务"),),
            note="金蝶官网旗下管易云品牌及官网链接已核对；历史管易/管易ERP统一到管易云。具体版本和合同服务保持自定义，未推定收费档位。",
        ),
        reference(
            "jushuitan",
            "聚水潭",
            (),
            "https://www.jushuitan.com/",
            "https://www.jushuitan.com/",
            (service("聚水潭服务"),),
            ("https://open.jushuitan.com/",),
        ),
        reference(
            "yonyou",
            "用友云",
            (),
            "https://www.yonyou.com/",
            "https://www.yonyou.com/success/yonsuite/pdfFile/standard.pdf",
            (service("用友YS云服务"),),
            note="用友YonSuite公开服务资料已核对。未将客户成功计划名称当作软件订阅套餐，实际授权规格按合同补充。",
        ),
        reference(
            "dingtalk",
            "钉钉",
            ("钉钉悟空",),
            "https://www.dingtalk.com/",
            "https://wukong.dingtalk.com/docs/quick-start/pricing-and-plans/",
            (
                service(
                    "钉钉悟空",
                    ("免费体验", "个人普通会员", "个人高级会员", "企业会员"),
                    "subscription",
                ),
                service("钉钉", ("标准版", "专业版", "专属版", "混合版"), "subscription"),
            ),
            ("https://www.dingtalk.com/?lwfrom=20150130160830727",),
            note="钉钉与悟空合并提供方，作为不同服务维护套餐。悟空标准/全功能+API接入等历史登记文字保留为实际自定义内容，不冒充官网档位。",
        ),
        reference(
            "aliyun",
            "阿里云",
            (),
            "https://www.aliyun.com/",
            "https://help.aliyun.com/zh/ocr/product-overview/product-billing/",
            (
                service("阿里云 OCR", ("按量付费", "专用资源包", "共享资源包"), "usage"),
                service("阿里云 OSS", ("按量付费", "资源包"), "usage"),
                service("阿里云服务"),
            ),
            ("https://help.aliyun.com/zh/oss/billing-method/",),
        ),
        reference(
            "alibaba-ip",
            "阿里知识产权保护平台",
            (),
            "https://ipp.alibabagroup.com/",
            "https://activity.alibaba.com/page/ipr_qa_detail01.html",
            (),
            ("https://survey.alibaba.com/survey/kwlXeGUWS",),
        ),
        reference(
            "pinduoduo",
            "拼多多",
            (),
            "https://ipp.pinduoduo.com/",
            "https://pfile.pddpic.com/galerie-go/mms_file/3a0bdcc8-0b73-4cb4-ae9c-ff34facaed2c.pdf",
            (service("拼多多知识产权维权服务"),),
        ),
        reference(
            "weibo",
            "微博",
            (),
            "https://weibo.com/",
            "https://service.account.weibo.com/h5/roles/gongyue",
            (service("微博服务"),),
        ),
        reference(
            "douyin",
            "抖音",
            (),
            "https://ippro.bytedance.com/",
            "https://www.douyin.com/draft/douyin_agreement/infringement_guide.html",
            (service("抖音知识产权维权服务"),),
            ("https://ippro.bytedance.com/view/?from=buying_helps",),
        ),
    )
    return (*rows, *extra)


def api_target(provider, subscription):
    rules = {
        "OpenAI": ("ChatGPT API", "OpenAI API"),
        "Anthropic": ("Claude API", "Claude API"),
        "Google": ("Gemini API", "Gemini API"),
        "xAI": ("Grok API", "Grok API"),
    }
    rule = rules.get(provider)
    name = (subscription or "").strip().casefold()
    if rule and (name == rule[0].casefold() or name.startswith(rule[0].casefold() + " ")):
        return rule[1]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--actor-id", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-digest")
    parser.add_argument("--readback", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        user = db.get(User, args.actor_id)
        if (
            not user
            or not user.is_active
            or user.archived_at
            or not get_access_context(user, db).is_global_manager
        ):
            raise RuntimeError("需要已验证的真实资产管理员")
        db.execute(
            text(
                "LOCK TABLE providers, platforms, service_products, service_instances, "
                "platform_tenants, asset_platform_links, import_proposed_objects "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
        )
        if args.readback:
            platforms = list(db.scalars(select(Platform).where(Platform.archived_at.is_(None))))
            rows = [directory_record(db, p).model_dump(mode="json") for p in platforms]
            linked = {p.provider_id for p in platforms}
            rows += [
                provider_record(p).model_dump(mode="json")
                for p in db.scalars(select(Provider).where(Provider.archived_at.is_(None)))
                if p.id not in linked
            ]
            print(
                json.dumps(
                    {"directory": sorted(rows, key=lambda x: (x["name"], x["id"]))},
                    ensure_ascii=False,
                )
            )
            db.rollback()
            return

        def invariants():
            return list(
                db.execute(
                    text(
                        "select (to_jsonb(t)-'service_product_id'-'purchase_platform_id'"
                        "-'updated_at')::text from service_instances t order by id"
                    )
                ).scalars()
            )

        before_instances = invariants()
        facts = references()
        catalog_cleanup.REFERENCES = facts
        report = catalog_cleanup.cleanup_catalog(db, actor_id=user.id, review=False)
        additions = []
        for instance, product, provider in db.execute(
            select(ServiceInstance, ServiceProduct, Provider)
            .join(ServiceProduct, ServiceInstance.service_product_id == ServiceProduct.id)
            .join(Provider, ServiceProduct.provider_id == Provider.id)
            .order_by(ServiceInstance.id)
        ):
            target = api_target(provider.name, instance.subscription_name)
            if not target or product.name == target:
                continue
            dest = db.scalar(
                select(ServiceProduct).where(
                    ServiceProduct.provider_id == provider.id,
                    ServiceProduct.name == target,
                    ServiceProduct.archived_at.is_(None),
                )
            )
            if not dest or dest.platform_id != product.platform_id:
                raise RuntimeError("API服务归属核对失败")
            additions.append(
                dict(
                    object_type="service_instances",
                    id=str(instance.id),
                    before={"service_product_id": str(instance.service_product_id)},
                    after={"service_product_id": str(dest.id)},
                )
            )
            instance.service_product_id = dest.id
        db.flush()
        for spec in facts:
            platform = db.scalar(
                select(Platform).where(
                    Platform.name == spec["name"], Platform.archived_at.is_(None)
                )
            )
            if not platform:
                continue
            if platform.description != spec["note"]:
                additions.append(
                    dict(
                        object_type="platforms",
                        id=str(platform.id),
                        before={
                            "description": platform.description,
                            "review_status": platform.review_status,
                        },
                        after={
                            "description": spec["note"],
                            "review_status": "pending_review",
                        },
                    )
                )
                platform.description = spec["note"]
                platform.review_status = "pending_review"
            db.flush()
            snapshot = directory_record(db, platform).model_dump(mode="json")
            expected = {s["name"]: (s["billing"], list(s["plans"])) for s in spec["services"]}
            if len(snapshot["services"]) != len(expected) or any(
                expected.get(s["name"]) != (s["billing_mode"], s["plan_options"])
                or s["provider_id"] != str(platform.provider_id)
                for s in snapshot["services"]
            ):
                continue
            if platform.review_status == "approved":
                continue
            evidence = dict(
                decision="approved",
                note=spec["note"],
                source_url=spec["source"],
                source_urls=[spec["source"], *spec.get("extra_sources", ())],
            )
            platform.review_status = "approved"
            report["reviews"].append(
                dict(
                    id=str(platform.id),
                    name=platform.name,
                    revision=snapshot["revision"],
                    **evidence,
                )
            )
            db.add(
                AuditLog(
                    actor_user_id=user.id,
                    action="directory.review",
                    object_type="platform",
                    object_id=platform.id,
                    request_id="catalog-curation-20261010:" + spec["code"],
                    before_data=snapshot,
                    after_data=evidence,
                )
            )
        db.flush()
        if invariants() != before_instances:
            raise RuntimeError("历史套餐、付款、日期或资产记录发生非预期改变")
        if additions:
            db.add(
                AuditLog(
                    actor_user_id=user.id,
                    action="directory.cleanup",
                    object_type="service_catalog",
                    request_id="catalog-curation-20261010",
                    after_data={
                        "changes": additions,
                        "sources": jsonable_encoder(facts),
                    },
                )
            )
        report["changes"] += additions
        platforms = list(db.scalars(select(Platform).where(Platform.archived_at.is_(None))))
        linked = {p.provider_id for p in platforms}
        report["pending"] = [
            dict(
                id=str(p.id),
                name=p.name,
                reason="未确认实际提供方、官方服务或合同套餐；按用户要求先跳过",
            )
            for p in platforms
            if p.review_status != "approved"
        ]
        report["pending"] += [
            dict(id=str(p.id), name=p.name, reason="同名历史提供方待核对；先跳过")
            for p in db.scalars(select(Provider).where(Provider.archived_at.is_(None)))
            if p.id not in linked
        ]
        report["pending"].sort(key=lambda item: (item["name"], item["id"]))
        report["reviews"].sort(key=lambda item: item["id"])
        report["historical_subscription_fields_preserved"] = True
        stable = json.loads(json.dumps(jsonable_encoder(report)))
        for change in stable["changes"]:
            for state in ("before", "after"):
                if "archived_at" in change.get(state, {}):
                    change[state]["archived_at"] = bool(change[state]["archived_at"])
        fingerprint = digest(stable)
        if args.apply:
            if args.expected_digest != fingerprint:
                raise RuntimeError("预览摘要不匹配；请重新核对目录")
            db.commit()
        else:
            db.rollback()
        print(
            json.dumps(
                {
                    "applied": args.apply,
                    "digest": fingerprint,
                    **jsonable_encoder(report),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
