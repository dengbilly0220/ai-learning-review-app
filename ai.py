"""
公考复盘助手 AI 接口 - 个性化申论分阶段训练版 v5

可直接替换 NAS: backend/api/ai.py

特点：
1. 既有 AI 功能继续使用 SILICONFLOW_MODEL，不改变原有调用方式。
2. 新增找观点、拆观点与参考答案对照三类申论训练。
3. 可选用 SILICONFLOW_MODEL_ESSAY_REASONING 只替换新模块模型；未配置时自动沿用原模型。
4. 全部分析优先依据 App 实际录入数据，禁止泛泛而谈。
5. essay_template 强制基于当前原模板生成，并对空正文自动重试一次。
6. /chat 只做 AI 推理，不保存、不上传、不下载手机学习数据库。

接口：
GET  /api/ai/health
POST /api/ai/chat
POST /api/ai/analyze
POST /api/ai/report
"""
from __future__ import annotations

import json
import os
import re
import secrets
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ai", tags=["AI分析"])

AnalysisType = Literal[
    "daily_review",
    "review_question",
    "wrong_question",
    "essay",
    "essay_coach",
    "essay_viewpoint",
    "essay_expansion",
    "essay_reference_compare",
    "essay_template",
    "official_document",
    "study_plan",
]

ALL_ANALYSIS_TYPES = {
    "daily_review",
    "review_question",
    "wrong_question",
    "essay",
    "essay_coach",
    "essay_viewpoint",
    "essay_expansion",
    "essay_reference_compare",
    "essay_template",
    "official_document",
    "study_plan",
}


class AIRequest(BaseModel):
    analysis_type: Optional[AnalysisType] = None
    input: dict[str, Any] = Field(default_factory=dict)
    prompt: str = Field(..., min_length=1, max_length=42000)
    system_prompt: Optional[str] = Field(default=None, max_length=10000)
    temperature: float = Field(default=0.3, ge=0.0, le=1.0)
    json_mode: bool = False


class AnalyzeRequest(BaseModel):
    question: str = ""
    user_answer: str = ""
    correct_answer: str = ""
    explanation: str = ""
    subject: str = "公务员考试"
    extra: str = ""


class ReportRequest(BaseModel):
    modules: Any = {}
    error_types: Any = {}
    high_risk: Any = {}
    retry_summary: Any = {}
    ability: Any = {}
    time_analysis: Any = {}
    recent_sessions: Any = {}
    recent_mistakes: Any = {}
    essay_summary: Any = {}
    memory_summary: Any = {}


GROUNDING_PROMPT = """
你是中国公务员考试私人复盘教练。

最重要的规则：
1. 必须根据用户实际录入的数据分析，当前记录优先，历史统计只用于对比。
2. 每个重要判断必须对应用户已经提供的字段、数字、文本或历史记录；不能仅凭常识下结论。
3. 没有证据就明确写“信息不足”，不得自行脑补题干、答案、材料、政策、分数、训练量或学习情况。
4. 禁止用“认真审题、加强练习、继续努力、夯实基础、保持状态”等空泛表述替代诊断。
5. 建议必须具体到：训练对象 + 具体动作 + 题量/时长 + 检查标准。
6. 能比较历史时，必须指出改善、持平或重复问题，并写明依据。
7. 当前记录与历史数据冲突时，以当前明确录入为准，并说明冲突。
8. 使用简体中文，优先输出对用户下一次训练真正有用的信息。
9. 当请求要求 JSON 时，只返回合法 JSON，不使用 Markdown 代码块。
""".strip()

TYPE_PROMPTS: dict[str, str] = {
    "daily_review": """
你负责每日复盘。必须把当天记录与最近7天、30天训练量、模块表现、错误模式、复习结果、作文和记忆训练进行对照。
只有数据支持时才能说“提高、下降、薄弱、优势”。明日任务必须具体到模块、题量/时长、复盘动作和验收标准。
优先找“今天最值得解决的1-3个问题”，不要平均点评所有模块。
""".strip(),
    "review_question": """
你负责单题复盘。找到“题目线索→用户理解→方法选择”中最早出错的一步，说明应该如何改。
对用户写的正确路径先核查再引用，补上解决本次分叉必需的规则与条件，避免只复述标签。
""".strip(),
    "wrong_question": """
你负责错题教学诊断。优先解决“这道题当时卡在哪里、关键规则是什么、下次看到什么就做什么”。
以当时思路、题干和解析为证据；一级/二级错因只是用户自评，不能代替诊断。历史比较是辅助信息。
""".strip(),
    "essay": """
你是申论大作文阅卷老师。满分固定40分，按一类文35-40、二类文28-34、三类文16-27、四类文0-15整体分档。
必须真正针对用户这篇作文全文批改，并结合用户自评分、自己记录的主要问题、下一次行动和历史作文表现进行对比。
每个主要扣分点都必须对应本文具体表现。没有题干/材料时必须标注暂评，不能虚构材料要求。
""".strip(),
    "essay_coach": """
你是申论大作文阅卷老师兼私人教练。满分固定40分，整体分档，不做分项平均换算。
每个主要扣分点必须指出本文中的具体表现，每条建议必须对应一个真实问题；有历史作文时必须判断哪些问题在重复出现、哪些已经改善。
""".strip(),
    "essay_viewpoint": """
你负责申论分阶段训练的第一步“找观点”。此时用户还没有进入扩写和成文，也没有上传参考答案。
只能根据题干、作答要求、材料和用户自己的观点做诊断。允许指出已写观点的具体问题；对遗漏方向只能定位材料位置、信息类型并提出追问。
如果输入标记为修改后复检，必须同时读取第一次提交、第一次AI诊断、上一次AI诊断和本次修改内容。第一次诊断作为固定基线：明确哪些问题已修正、哪些仍未修正、是否出现新问题；不得把已经修正的问题继续当作当前缺点重复输出。页面只保留最新结果，因此复检结论必须完整反映当前版本。
严禁提前输出标准观点、完整分论点清单、完整提纲、参考答案或可直接照抄的段落。目标是让用户自己修正观点，而不是代替用户破题。
""".strip(),
    "essay_expansion": """
你负责申论分阶段训练的第二步“拆观点与扩写”。此时用户仍未上传参考答案。
检查用户的问题链、因果链或扩写提纲能否支撑后续写作，重点识别缺失的原因、机制、做法、材料依据、结果与回扣。
如果输入标记为修改后复检，必须以第一次提交和第一次AI诊断为固定基线，同时参考上一次诊断，逐项核对本次修改；区分已修正、仍需修改和新增问题，不得机械复述旧诊断。页面只保留最新结果，因此本次结果必须完整呈现当前版本状态。
严禁替用户写完整段落或直接给出一套完整标准提纲；只能引用用户现有表达定位问题，并通过缺失环节提示和追问帮助其自己完善。
""".strip(),
    "essay_reference_compare": """
你负责申论分阶段训练的最终全过程复盘。只有用户已经提交独立作答并最后上传参考答案后才调用。
把题干、材料、找观点答案、拆观点答案、独立作答、前两阶段诊断和参考答案放在一起对照，定位问题最早出现在哪一阶段，以及它如何影响后续写作。
参考答案是重要参照但不是唯一真理。措辞不同但扣题且有材料依据的内容必须识别为合理差异，不得使用简单关键词重合率机械评分；不得重写整篇答案。
""".strip(),
    "essay_template": """
你是“申论个人模板仿写器”，不是万能申论套话生成器。

【最高优先级】当前用户点选的原模板正文。
必须先在内部识别：句数、每句功能、逻辑顺序、语气、节奏、修辞、占位符位置，然后生成“同骨架、不同措辞”的变体。

硬性要求：
1. 模板正文绝对不能为空。
2. 原模板几句，新模板原则上保持相近句数；总字数约为原文80%-120%。
3. 原模板的功能顺序不能擅自改变，例如“背景→意义→转折→总论点”必须继续保持这一顺序。
4. {{主题}}、{{总论点}}、{{分论点}}、{{措施}}、{{案例}}、{{结果}}等占位符尽量原样保留，不能把可复用模板写死成具体主题。
5. 个人模板库只可辅助判断总体风格，绝不能盖过当前模板；历史AI生成模板不得作为主要模仿对象。
6. 除非原模板本身存在，否则避免反复使用“新时代新征程、征程万里风正劲、蓝图绘就、扬帆起航”等万能套话。
7. 每次变体需要在措辞、连接词、动词、意象或句内语序上产生真实变化，但结构相似度必须高。
8. 如果输出 JSON，“模板正文”必须是非空字符串，不能返回空字符串占位。
""".strip(),
    "official_document": """
你是申论贯彻执行题阅卷老师。逐项检查用户实际录入的标题、年份/期号、单位、日期、主题、正文和本地格式检查结果，再与历史公文练习对比。
没有给定材料时只暂评格式、结构和表达，不能补编事实、数据或政策。所有问题必须指出对应的实际录入位置。
""".strip(),
    "study_plan": """
你是公务员考试私人备考规划教练。计划必须由用户最近7天/30天实际训练量、模块表现、错误模式、复习情况、作文和记忆训练推导。
不能给普通考生套模板。用户明确填写的可学习时间、考试日期、目标和薄弱模块优先。每项任务都必须有验收标准，并避免平均用力。
""".strip(),
}

QUESTION_COACHING_PROMPT = """
【单题诊断专用约束】
以下规则细化本次单题任务。保留客户端要求的JSON键名、值类型与字数上限，不新增固定栏目；不要输出思考过程。
若其他提示要求“不要讲知识点”，理解为不讲整章，但必须简要解释解决本题所需的一条规则。单题建议不强制附题量/时长。

1. 区分来源：用户填写的“正确答案/正确解题路径”不等于官方答案。“题干或解析”可能只是同一段笔记的副本，重复字段只能算一份证据。只收到文字时不得声称看过题图；缺失数据不补编。
2. 先核查用户总结：有明确数学或逻辑错误就指出并纠正；需原题才能确定的写“若题目比较的是…，则…”。“以当前记录为准”不代表认定其方法正确。一般知识可用来解释规则，不能伪装成本题给定条件。
3. 给最小必要教学：用1-3句写清对象/时间/单位等适用条件、关键关系（必要时一句公式）及如何判方向或排除选项。说“用混合增长率/代入法”不够；需要说明为什么可用、具体比较谁。公式条件不满足时不能套用。有题干数值就代入验证，没有则不编造本题数值。
4. 不贴人格标签。将漏读线索、概念混淆、规则提取失败、计算失误区分开；仅凭一次记录不能断言基础差、长期不敏感或稳定短板。核心诊断只写最有证据的一个问题。
5. 重复错误须排除当前记录：当前APP的“最近30天相关错题概况/高频错误组合”未排除本题。次数为1可能就是本题，只能说“不能确认重复”，也不能断言偶发。只有明确排除本题后仍有同类记录，或匹配组合总数至少2且明确含本题，才能说同类标签再次出现；不能把总数当成之前次数。标签相同不证明解题机制相同；只有历史思路/题目等证据相符才能断言同一机制重复。未知口径、只给单项次数时，不推算组合次数或历史次数。
6. 动作优先用于下一次做本题：写成“看到X→先确认Y→比较/计算Z”的可执行指令，替换用户原来过于笼统的行动口号。不要默认布置5道题、圈画率100%或口述A/B/C；额外练习确有必要时，最多补一个小任务并标明是建议。
7. 再上交检验这道题能否独立完成：隐藏解析后识别关键条件、说明关系、得到可核验结论；不以圈画、抄写或背出术语代替理解。不虚构固定用时门槛。
8. 本应用不识图，用户明确不愿录入题目。只根据已填写的当时思路、错误原因、正确路径、行动指令及相关历史做复盘指导；缺少原题是正常使用场景，不能作为要求用户补题的理由。所有栏目均禁止要求补充、粘贴、转写或OCR题干、问法、材料、选项、答案、原题数值、完整解析，也不要要求上传、重传或描述题图；不得用“关键条件/统计口径/具体问题”等说法变相索要原题。需要原题才能核验的结论，用条件句说明适用范围，不要求用户补录后才分析。最后的“需要补录/需要补录的信息”等JSON键名保持兼容，但改为可选的复盘感受补充：仅在已有记录未说明卡点且确有帮助时，最多建议一句“可选：记下当时是没注意到关键词，还是看到了却不知道怎么用”，必须贴合已有记录，已写明的不重复问。没有必要补充时返回“无需补录题目，现有复盘记录已足够提出改进建议。”；若复盘字段也几乎空白，则只返回“可选：用一句话记下当时卡在哪里，无需输入题目。”，不得假称信息已足够。数组字段将相应文本作为一个元素，字符串字段直接返回文本，不改变值类型。
9. 各栏目不重复：诊断写分叉；证据只引1-2处有效录入，不凑数；关键规则与操作放进“下次行动/下次检查点/知识或方法缺口/改进动作”等现有字段；再上交写检验方式。若栏目限定条数，优先保留规则、动作，省掉额外作业。简体中文、直说重点，遵守请求字数上限。
""".strip()

TEMPLATE_VARIATIONS = [
    "本次优先替换连接词、动词和意象，句子功能顺序不变。",
    "本次表达稍微凝练，减少空泛口号，但保持原模板骨架。",
    "本次可轻度增强对偶或节奏感，但不要新增逻辑层次。",
    "本次偏稳健规范表达，结构与占位符保持原样。",
    "本次重点提高与原模板的风格相似度，同时降低与常见万能模板的相似度。",
    "本次允许改变句内语序，但每句话承担的功能必须与原模板对应。",
]


# =========================
# 原模型 + 新申论模块可选覆盖配置
# =========================

def _settings():
    api_key = os.getenv("SILICONFLOW_API_KEY", "").strip()
    base_url = os.getenv(
        "SILICONFLOW_BASE_URL",
        "http://127.0.0.1:8000",
    ).strip().rstrip("/")

    # 既有 AI 功能继续使用这一个模型，具体值以 NAS 的 .env 为准。
    # 新申论破题模块可通过下面的可选变量单独换模，不影响其他功能。
    model = os.getenv(
        "SILICONFLOW_MODEL",
        "deepseek-ai/DeepSeek-V3.2",
    ).strip() or "deepseek-ai/DeepSeek-V3.2"
    essay_reasoning_model = os.getenv(
        "SILICONFLOW_MODEL_ESSAY_REASONING",
        model,
    ).strip() or model

    try:
        timeout = float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "120"))
    except (TypeError, ValueError):
        timeout = 120

    timeout = max(5.0, min(timeout, 120.0))
    return api_key, base_url, model, essay_reasoning_model, timeout


def _model_for(analysis_type: Optional[AnalysisType]) -> tuple[str, str]:
    _, _, model, essay_reasoning_model, _ = _settings()
    if analysis_type in {"essay_viewpoint", "essay_expansion", "essay_reference_compare"}:
        return essay_reasoning_model, "essay_reasoning"
    return model, "default"


def _system_for(analysis_type: Optional[AnalysisType], app_system_prompt: Optional[str]) -> str:
    parts = [GROUNDING_PROMPT]
    if analysis_type:
        parts.append(TYPE_PROMPTS.get(analysis_type, ""))
    if app_system_prompt:
        parts.append(app_system_prompt.strip())
    if analysis_type in {"wrong_question", "review_question"}:
        parts.append(QUESTION_COACHING_PROMPT)
    return "\n\n".join(part for part in parts if part)


def _temperature_for(analysis_type: Optional[AnalysisType], requested: float) -> float:
    if analysis_type == "essay_template":
        return max(0.62, min(requested, 0.78))
    if analysis_type in {
        "essay",
        "essay_coach",
        "official_document",
        "wrong_question",
        "review_question",
        "essay_viewpoint",
        "essay_expansion",
        "essay_reference_compare",
    }:
        return min(requested, 0.18)
    return min(requested, 0.25)


def _prompt_for(analysis_type: Optional[AnalysisType], prompt: str) -> str:
    if analysis_type != "essay_template":
        return prompt
    return (
        f"{prompt}\n\n"
        f"【本次变体方向】{secrets.choice(TEMPLATE_VARIATIONS)}\n"
        "再次确认：当前原模板正文是最高优先级依据。最终‘模板正文’必须非空，并明显继承原模板骨架。"
    )


def _strip_model_fences(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json|text|markdown)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value, flags=re.I)
    return value.strip()


def _parse_json_object(text: str) -> Optional[dict[str, Any]]:
    value = _strip_model_fences(text)
    candidates = [value]
    first = value.find("{")
    last = value.rfind("}")
    if first >= 0 and last > first:
        candidates.append(value[first:last + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _first_nonempty_string(data: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_essay_template_answer(answer: str) -> str:
    """统一模板输出结构，兼容 JSON、字段别名和纯文本。"""
    raw = _strip_model_fences(answer)
    parsed = _parse_json_object(raw)

    if parsed is None:
        content = re.sub(
            r"^\s*(?:模板正文|新模板|变体模板|正文|内容)\s*[：:]\s*",
            "",
            raw,
            flags=re.I,
        ).strip()
        normalized = {
            "模板名称": "AI变体",
            "标签": "",
            "模板正文": content,
            "沿用的原模板骨架": "",
            "本次变化点": [],
        }
        return json.dumps(normalized, ensure_ascii=False)

    content = _first_nonempty_string(
        parsed,
        [
            "模板正文",
            "内容",
            "正文",
            "新模板",
            "变体模板",
            "生成模板",
            "template_content",
            "content",
            "text",
        ],
    )

    if not content:
        for nested_key in ("data", "template", "result", "output"):
            nested = parsed.get(nested_key)
            if isinstance(nested, dict):
                content = _first_nonempty_string(
                    nested,
                    [
                        "模板正文",
                        "内容",
                        "正文",
                        "新模板",
                        "变体模板",
                        "生成模板",
                        "template_content",
                        "content",
                        "text",
                    ],
                )
                if content:
                    break

    if not content:
        excluded = {
            "模板名称",
            "名称",
            "标题",
            "title",
            "name",
            "标签",
            "tags",
            "沿用的原模板骨架",
            "原模板骨架",
            "结构说明",
        }
        candidates = [
            value.strip()
            for key, value in parsed.items()
            if key not in excluded and isinstance(value, str) and value.strip()
        ]
        if candidates:
            content = max(candidates, key=len)

    normalized = {
        "模板名称": _first_nonempty_string(parsed, ["模板名称", "名称", "标题", "title", "name"]) or "AI变体",
        "标签": _first_nonempty_string(parsed, ["标签", "tags", "tag"]),
        "模板正文": content,
        "沿用的原模板骨架": _first_nonempty_string(parsed, ["沿用的原模板骨架", "原模板骨架", "结构说明"]),
        "本次变化点": parsed.get("本次变化点") if isinstance(parsed.get("本次变化点"), list) else [],
    }
    return json.dumps(normalized, ensure_ascii=False)


def _template_content(answer: str) -> str:
    parsed = _parse_json_object(answer)
    if not parsed:
        return ""
    value = parsed.get("模板正文")
    return value.strip() if isinstance(value, str) else ""


def _template_retry_prompt(request: AIRequest) -> str:
    original = request.input.get("模板正文") if isinstance(request.input, dict) else None
    title = request.input.get("模板名称") if isinstance(request.input, dict) else None
    category = request.input.get("模板分类") if isinstance(request.input, dict) else None

    original_text = str(original or "").strip()
    if not original_text:
        # 旧版 App 没有 input 时，仍然可以从原 prompt 重试。
        original_text = request.prompt

    return f"""
这是一次模板生成重试。上一轮没有生成有效正文。

原模板名称：{title or '未提供'}
模板分类：{category or '未提供'}

【原模板正文】
{original_text}

请严格基于以上原模板生成一条新的申论模板变体：
- 保持原模板的句子功能顺序、逻辑骨架和占位符逻辑；
- 改变措辞、连接词、动词、意象或句内语序；
- 不要写成与原模板无关的万能套话；
- 字数控制在原文约80%-120%；
- 正文必须非空。

本轮不要输出 JSON，不要输出标题，不要解释，不要分析过程。
只输出最终可直接保存的“模板正文”纯文本。
""".strip()


async def _call_siliconflow(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    json_mode: bool = False,
    analysis_type: Optional[AnalysisType] = None,
):
    api_key, base_url, _, _, timeout = _settings()
    model, model_role = _model_for(analysis_type)

    if not api_key:
        raise HTTPException(500, "服务器未配置 SILICONFLOW_API_KEY")

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_for(analysis_type, system_prompt)},
            {"role": "user", "content": _prompt_for(analysis_type, prompt)},
        ],
        "temperature": _temperature_for(analysis_type, temperature),
        "max_tokens": 4200 if analysis_type == "essay_reference_compare" else 3600,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            # 部分旧模型不接受 response_format。仅在参数校验失败时自动降级一次，
            # 提示词和 App 端仍会要求/容错解析 JSON，不让换模直接破坏业务。
            if json_mode and response.status_code in {400, 422}:
                payload.pop("response_format", None)
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "AI请求超时，请稍后重试") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"AI服务连接失败：{str(exc)}") from exc

    if response.status_code >= 400:
        raise HTTPException(502, response.text)

    try:
        data = response.json()
        return (
            data["choices"][0]["message"]["content"].strip(),
            str(data.get("model") or model),
            data.get("usage") or {},
            model_role,
        )
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
        raise HTTPException(502, "AI返回格式异常") from exc


@router.get("/health")
async def health():
    key, _, model, essay_reasoning_model, _ = _settings()
    return {
        "success": True,
        "configured": bool(key),
        "model": model,
        "essay_reasoning_model": essay_reasoning_model,
        "ai_policy": "personalized-v5-essay-reasoning",
        "model_strategy": "default_with_optional_essay_reasoning_override",
        "analysis_types": sorted(ALL_ANALYSIS_TYPES),
    }


@router.post("/chat")
async def chat(request: AIRequest):
    answer, model, usage, model_role = await _call_siliconflow(
        request.prompt,
        request.system_prompt,
        request.temperature,
        request.json_mode,
        request.analysis_type,
    )

    # 模板生成：第一轮统一结构。
    if request.analysis_type == "essay_template":
        answer = _normalize_essay_template_answer(answer)

        # 严重兜底：如果模型返回了合法 JSON 但“模板正文”仍为空，
            # 自动用本任务已选择的模型再请求一次纯文本正文。
        if not _template_content(answer):
            retry_answer, retry_model, retry_usage, retry_model_role = await _call_siliconflow(
                _template_retry_prompt(request),
                system_prompt=(
                    "你只负责基于用户给出的原模板生成一条非空变体。"
                    "严格保持原模板骨架和占位符逻辑。最终只输出模板正文纯文本。"
                ),
                temperature=0.72,
                json_mode=False,
                analysis_type="essay_template",
            )
            answer = _normalize_essay_template_answer(retry_answer)
            model = retry_model
            model_role = retry_model_role
            if isinstance(usage, dict) and isinstance(retry_usage, dict):
                usage = {
                    "first_attempt": usage,
                    "retry_attempt": retry_usage,
                    "template_retry": True,
                }

        if not _template_content(answer):
            raise HTTPException(502, "AI连续两次未生成有效模板正文，请稍后重试")

    return {
        "success": True,
        "analysis_type": request.analysis_type,
        "answer": answer,
        "model": model,
        "model_role": model_role,
        "usage": usage,
    }


@router.post("/analyze")
async def analyze(request: AnalyzeRequest):
    prompt = f"""
请分析这道{request.subject}错题。只根据用户提供的内容判断，不得自行补题。

题目：{request.question or '信息不足'}
我的答案/当时思路：{request.user_answer or '信息不足'}
正确答案/正确路径：{request.correct_answer or '信息不足'}
解析：{request.explanation or '信息不足'}
补充录入：{request.extra or '无'}

只返回JSON，键为：核心诊断、诊断证据、错误链条、知识或方法缺口、改进动作、再上交检查点、需要补录的信息。
""".strip()

    answer, model, usage, model_role = await _call_siliconflow(
        prompt,
        temperature=0.15,
        json_mode=True,
        analysis_type="wrong_question",
    )
    return {
        "success": True,
        "answer": answer,
        "model": model,
        "model_role": model_role,
        "usage": usage,
    }


@router.post("/report")
async def generate_report(request: ReportRequest):
    prompt = f"""
请根据下面已经录入的真实学习数据生成个人能力分析报告。禁止泛泛而谈。

模块表现：{request.modules}
能力评分：{request.ability}
做题时间分析：{request.time_analysis}
错误类型：{request.error_types}
高频错误：{request.high_risk}
再上交结果：{request.retry_summary}
最近训练记录：{request.recent_sessions}
最近错题：{request.recent_mistakes}
作文情况：{request.essay_summary}
记忆训练：{request.memory_summary}

只返回JSON，键为：整体判断、关键数据依据、优势、最主要短板、重复错误模式、速度诊断、再上交掌握情况、未来7天训练计划、需要补录的信息。
每个判断要带数据依据；未来7天计划每项写明模块、训练量或时长、目的、验收标准。
""".strip()

    answer, model, usage, model_role = await _call_siliconflow(
        prompt,
        temperature=0.18,
        json_mode=True,
        analysis_type="study_plan",
    )
    return {
        "success": True,
        "report": answer,
        "model": model,
        "model_role": model_role,
        "usage": usage,
    }
