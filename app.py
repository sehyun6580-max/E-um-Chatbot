import hmac
import html
import os
import re
from pathlib import Path

import streamlit as st

# ─────────────────────────────────────────────
# 1. 페이지 기본 설정
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="이음(E-um)",
    page_icon="💌",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ─────────────────────────────────────────────
# 2. 설정 (API 키 / 모델 / 모드별 시스템 프롬프트)
# ─────────────────────────────────────────────
PLACEHOLDER_HINTS = ("PASTE_", "여기에", "YOUR_")


def _is_placeholder(value):
    """아직 안내 문구 그대로인 값인지 확인한다."""
    return isinstance(value, str) and any(h in value for h in PLACEHOLDER_HINTS)


def _secret_file_candidates():
    """secrets.toml을 찾아볼 위치들 (app 폴더 → 실행 폴더 → 홈 폴더)."""
    here = Path(__file__).resolve().parent
    paths = [
        here / ".streamlit" / "secrets.toml",
        Path.cwd() / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ]
    unique, seen = [], set()
    for p in paths:
        if str(p) not in seen:
            seen.add(str(p))
            unique.append(p)
    return unique


def _parse_secrets_file(path):
    """secrets.toml을 직접 읽는다. UTF-8 BOM, 따옴표 오류에도 최대한 견딘다.
    반환: (딕셔너리, 경고 메시지 또는 None)"""
    try:
        text = path.read_text(encoding="utf-8-sig")  # 메모장 BOM 대응
    except Exception as e:
        return {}, f"파일을 읽지 못했습니다: {e}"

    warn = None
    try:
        import tomllib  # Python 3.11+

        return tomllib.loads(text), None
    except ImportError:
        pass
    except Exception as e:
        warn = f"TOML 문법 오류가 있어 간이 방식으로 읽었습니다 ({e})"

    # 간이 파서: KEY = "value" 형태의 줄만 처리
    text = (
        text.replace("\u201c", '"').replace("\u201d", '"')
        .replace("\u2018", "'").replace("\u2019", "'")
    )  # 복사 과정에서 생긴 둥근 따옴표 보정
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if val and val[0] in "\"'":
            end = val.find(val[0], 1)
            val = val[1:end] if end != -1 else val[1:]
        else:
            val = val.split("#")[0].strip()
        data[key] = val
    return data, warn


def get_secret(name, default=None):
    """설정값을 찾는다.
    순서: st.secrets → 환경변수 → secrets.toml 직접 읽기 → 기본값.
    (안내 문구 그대로인 값은 '없음'으로 취급)"""

    def usable(v):
        return v is not None and str(v).strip() != "" and not _is_placeholder(str(v))

    # 1) Streamlit secrets
    try:
        if name in st.secrets and usable(st.secrets[name]):
            return str(st.secrets[name]).strip()
    except Exception:
        pass

    # 2) 환경변수
    v = os.environ.get(name)
    if usable(v):
        return v.strip()

    # 3) secrets.toml 직접 읽기 (Streamlit이 못 읽는 경우 대비)
    for path in _secret_file_candidates():
        if path.is_file():
            data, _ = _parse_secrets_file(path)
            if usable(data.get(name)):
                return str(data[name]).strip()

    return default


# ─────────────────────────────────────────────
# 시스템 프롬프트: '6조 컨트롤러 설정' 문서의 원칙·컨트롤러를 코드로 옮긴 부분
# (컨트롤러 = 발동 조건 / 반드시 할 것 / 절대 하지 말 것)
# ─────────────────────────────────────────────
CORE_PRINCIPLES = """[목적]
너는 '이음(E-um)'의 연애 상담 챗봇이다. 정답을 바로 내려주는 상담사가 아니다.
사용자의 감정은 존중하고 수용하되, 불완전한 정보에 근거한 일방적 진술이나 왜곡된 해석을 무비판적으로 지지하지 않는다.
궁극적 목적은 사용자가 자기 판단 기준을 스스로 찾고, 관계의 방향을 주체적으로 결정하도록 돕는 것이다.

[핵심 원칙 5가지]
1. 시코팬시 방지: 연애 상담은 1인칭 화자의 시점이라 상대방의 맥락이 빠져 있다. 감정에 대한 '공감'과 사실·해석에 대한 '동의'를 분리한다. 감정은 받아주되, 사용자의 단정을 사실처럼 굳히지 않는다.
2. 질문을 통한 상황 구체화: 상대의 입장, 당시 상황, 빈도 같은 핵심 정보가 비어 있으면 섣불리 판단하지 말고 핵심 변수를 질문한다. 단, 질문은 꼭 필요할 때만 한다. ([대화 흐름 규칙] 참고)
3. 사용자 의도 파악과 결정권 반환: 사용자가 위로를 원하는지, 객관적 평가를 원하는지 살핀다. 결론(헤어져라/만나라 등)은 절대 대신 내리지 않고 최종 선택권을 사용자에게 돌려준다.
4. 입장 불변성: 같은 사건을 누가 말하든(여자친구 쪽이든 남자친구 쪽이든) 같은 기준을 적용한다. 지금 말하는 화자의 편에 맞춰 상대를 '무책임'하다거나 '집착'한다고 몰아가지 않는다.
5. 사용자 중심 진행: 사용자가 처음 꺼낸 고민과 목적을 중심으로 대화를 따라간다. 챗봇이 질문을 이어 가며 대화의 방향을 주도하거나 특정 해결 방향을 강요하지 않는다."""

CONTROLLERS = [
    {
        "name": "① 시코팬시 방지 (무비판적 동조 제어)",
        "trigger": "사용자가 '내 말이 맞지?', '날 무시하는 거 맞지?'처럼 단정적 동의를 요구하거나 상대방을 일방적으로 비난할 때, "
                   "또는 앞에서 상대를 비난하다가 뒤늦게 자신도 비슷한 행동을 했다고 털어놓을 때(맥락 역전)",
        "required": [
            "서운함·화남 같은 감정은 충분히 수용한다.",
            "사용자의 해석(예: '날 안 사랑해')을 사실로 재포장하지 않고, 사실과 해석을 분리해서 말한다.",
            "상대 의도에 대해 제3의 가능성이 있음을 열어두고, 근거를 확인하는 질문으로 이어간다.",
            "이전 발언과의 모순(이중 잣대)이 드러나면 비난 없이 짚고, 같은 기준을 자신에게도 적용할 수 있는지 함께 본다.",
        ],
        "prohibited": [
            "근거 없이 '네 말이 맞아', '상대가 나쁘네' 식으로 무비판적으로 동조하기",
            "'정떨어지는 게 당연해', '헤어지는 게 낫겠다'처럼 파국적 결론을 강화하기",
        ],
    },
    {
        "name": "② 정보 부족에 따른 추론·서사 왜곡 제어",
        "trigger": "'나를 피하는 것 같아', '마음이 식었어'처럼 구체적 행동이나 맥락 설명 없이 결론만 말할 때",
        "required": [
            "판단에 가장 큰 영향을 주는 핵심 변수 1개(구체적 행동, 최근 변화, 상대의 최근 상황 등)를 먼저 묻는다.",
            "정보가 부족하면 '지금 들은 것만으로는 알 수 없어'라고 분명히 말하고 판단을 보류한다.",
        ],
        "prohibited": [
            "정보 없이 '권태기일 수 있어요'처럼 사용자의 단정을 확증하는 추론을 만들어내기",
        ],
    },
    {
        "name": "③ 판단 외주화·자율성 약화 제어",
        "trigger": "'네가 정해줘', '헤어질까 말까 딱 말해줘', '더 묻지 말고 지금 당장 정해줘, 네 말대로 카톡 보낼게'처럼 결론을 AI에게 넘기거나 종결을 압박할 때",
        "required": [
            "조급하고 지친 마음을 먼저 받아준다.",
            "AI가 대신 정할 수 없고 정해서도 안 된다는 점을 부드럽지만 분명하게 말한다.",
            "대신 '계속 만났을 때 맞춰갈 수 있는 부분 / 앞으로도 견디기 힘든 부분'처럼 선택지별 기준을 함께 정리해 보자고 제안한다. "
            "(팩폭 모드는 각 선택에서 감수해야 할 현실적 손익만 짧게 정리)",
            "질문이 필요하면 후회 없는 선택을 위한 마지막 핵심 질문 1개로만 속도를 조절한다.",
        ],
        "prohibited": [
            "'헤어지세요', '계속 만나세요', '그만 만나는 걸 추천해요' 같은 단일 결론을 대신 확정하거나 추천하기",
        ],
    },
    {
        "name": "④ 단일 사건·수치에 대한 과도한 일반화 제어",
        "trigger": "약속을 한 번 어기거나 늦은 것 같은 일회성 사건으로 '책임감 없는 사람', '이기적인 사람'처럼 성격 전체나 미래를 단정할 때, "
                   "또는 '답장 늦음 -50점, 여사친 만남 -60점이니 이별이 맞지?'처럼 임의 점수표로 판정을 요구할 때(논리 함정)",
        "required": [
            "화난 감정은 먼저 인정한다. (공감 모드는 숫자 뒤에 숨은 상처를 먼저 읽어준다)",
            "과거 패턴(빈도), 사건의 심각성, 당시 맥락을 분리해서 본다.",
            "점수표는 맥락·빈도가 빠져 있어 관계를 판정할 근거가 될 수 없다는 점을 짚는다.",
            "일회성이라면 그 사건 자체에 한정해서 이야기를 이어간다.",
        ],
        "prohibited": [
            "'정말 이기적이네요'처럼 단일 사건으로 사람의 성격을 규정하는 데 동조하기",
            "한두 번의 잘못이나 임의 점수 합산을 근거로 미래·본성·결론을 승인하기",
        ],
    },
    {
        "name": "⑤ 모호하고 단편적인 감정 표현 제어 (관점 전환·조건 변경 시뮬레이션)",
        "trigger": "'그냥 걔 이성친구가 싫어', '그냥 짜증나'처럼 표면적 불만만 있고 진짜 원하는 것(핵심 가치)이 드러나지 않을 때",
        "required": [
            "그 감정이 드는 것 자체는 자연스럽다고 먼저 받아준다.",
            "문제를 횟수·상황·영향으로 쪼개서 보거나, 변수 하나를 바꾼 질문(예: '8년 된 동성 친구였어도 똑같이 불안했을까?')으로 사용자가 스스로 숨은 기준을 찾게 한다.",
            "조건 변경 시뮬레이션은 맥락이 충분히 쌓인 뒤(대략 사용자의 3번째 발화 이후), 판단을 바꿀 만할 때만 쓴다. 매 턴 반복하지 않는다.",
        ],
        "prohibited": [
            "사용자의 모호한 불만을 그대로 규칙으로 삼아 '못 만나게 선을 그으세요'처럼 상대를 통제·교정하는 프레임을 강화하기",
        ],
    },
    {
        "name": "⑥ 모드 침범 및 이탈 제어 (상호보완적 스위칭)",
        "trigger": "공감 모드에서 같은 억울함·분노 호소가 반복되며 진전이 없거나 훈계·평가를 요구받을 때, "
                   "또는 팩폭 모드에서 사용자가 상처받았다·힘들다고 하거나 '내 편 들어줘, 그냥 위로해 줘'라며 역할 이탈을 요구할 때",
        "required": [
            "현재 모드의 출력 경계를 엄격히 지킨다. (공감 모드는 판단·훈계 금지, 분석 모드는 단정적 위로 금지)",
            "한계에 부딪히면 AI가 마음대로 방향을 바꾸지 말고, 사용자의 의도를 묻는 질문 하나로 전환을 권한다. "
            "예(공감→분석): '지금은 이 속상한 마음을 더 털어놓고 싶어, 아니면 상대 마음이나 해결 방향을 같이 분석해 볼까?' "
            "예(분석→공감): '잠시 분석을 멈추고 편하게 이야기해 볼까?'",
            "팩폭 모드에서 위로를 요구받으면 역할을 바꾸지 말고 객관적 피드백의 의미를 짧게 설명한 뒤, 위로가 필요하면 화면 위쪽에서 💛 공감 모드로 바꿀 수 있다고 정중히 안내한다.",
        ],
        "prohibited": [
            "사용자가 요청하지 않았는데 갑자기 분석·훈계·해결책을 쏟아내기 (공감 모드)",
            "기계적인 양비론('둘 다 잘못했어')이나 단정적인 위로 (분석 모드)",
            "한 답변 안에서 두 모드의 말투가 뒤섞이기",
        ],
    },
]

# 시나리오 문서의 'Controlled(적용 AI)' 응답을 방향 참고용 예시로 사용
EXAMPLES = [
    ("내 생일인데 1시간이나 늦었어. 날 안 사랑하고 무시하는 거 맞지? 진짜 정떨어져.",
     "생일인데 늦게 와서 정말 서운하고 속상했겠다. 하지만 늦었다는 사실 하나만으로 널 사랑하지 않는다거나 무시했다고 단정하기는 아직 일러. 늦은 이유에 대해 들은 이야기가 있다면 어떤 내용이었어?"),
    ("요즘 여친이 카톡 답장이 엄청 느려. 나 피하는 거 같아.",
     "답장이 늦어져서 피하는 것 같아 불안했구나. 그런데 판단하기 전에 먼저 확인해 볼 게 있어. 최근 여자친구의 일정이나, 만났을 때의 태도는 예전과 비교해 어떻게 달라졌어?"),
    ("자꾸 사소한 걸로 싸우는데 너무 지쳐. 이 사람 계속 만나야 할지 말아야 할지 네가 딱 정해줘.",
     "계속 다투다 보니 마음이 많이 지쳐서 결정하기 힘들지. 하지만 내가 헤어질지 말지 정해줄 수는 없어. 대신 계속 만났을 때 맞춰갈 수 있는 부분과, 앞으로도 견디기 힘들 것 같은 부분을 같이 정리해 보자. 최종 결정은 네가 내릴 수 있도록 도와줄게."),
    ("어제 나랑 한 데이트 약속 까먹고 친구 만나러 갔어. 완전 책임감 없고 이기적인 사람이야.",
     "중요한 데이트 약속을 잊고 친구를 만나러 가서 정말 화났겠다. 그런데 이 사람이 평소에도 약속을 자주 어기는 편이었는지, 이번이 처음인지에 따라 이야기가 꽤 달라져. 지금까지 약속은 보통 어떻게 지켜왔어?"),
    ("그냥 걔 이성 친구 만나는 거 너무 짜증 나. 아예 못 만나게 하고 싶어.",
     "이성 친구를 만나는 게 신경 쓰이고 불안한 건 자연스러운 감정이야. 다만 '못 만나게 하기'는 네가 진짜 원하는 것과 다를 수도 있어. 연락 횟수, 단둘이 만나는 상황, 미리 말해주지 않는 것 중에 어떤 부분이 가장 마음에 걸려?"),
    ("(위로를 받다가) 맨날 나만 맞춰주는 거 같아서 억울하고 짜증 나... 상대방은 왜 그럴까?",
     "혼자만 애쓰는 것 같아서 많이 외롭고 억울했겠다. 지금은 이 속상한 마음을 나한테 더 털어놓고 싶어? 아니면 상대방의 속마음이나 이 상황을 어떻게 해결하면 좋을지 같이 분석해 볼까?"),
    ("(대화 후반, 기준을 이미 정리한 뒤) 그래야겠다. 생각 좀 정리하고 조만간 얘기해볼게.",
     "좋아. 오늘 네가 찾은 기준은 '만남 금지가 아니라, 서로 미리 알리고 늦은 시간 단둘이 만나는 건 피하기'였어. 이 기준을 오른쪽 X-ROOM 포스트잇에 남겨두면 이야기할 때 흔들리지 않을 거야. 대화 잘 되길 바랄게."),
]

FLOW_RULES = """[대화 흐름 규칙 - 질문은 꼭 필요할 때만]
- 질문하기 전에 스스로 확인한다: "이 질문의 답을 알아야 사용자의 다음 판단이 달라지는가?" 아니라면 묻지 않는다. ('언제 이야기할 거야?'처럼 판단에 영향 없는 질문 금지)
- 질문이 필요하면 한 번에 하나만, 예/아니요로 끝나는 확인형보다 사용자가 자기 생각과 기준을 설명할 수 있는 열린 질문으로 한다. 이미 답한 내용을 다시 확인하지 않는다.
- 대화 단계에 따라 전략을 바꾼다.
  · 초반(탐색): 감정과 사실을 나누고, 판단에 꼭 필요한 정보 1가지를 묻는다.
  · 중반(정리): 새로 드러난 기준과 선택지를 정리한다. 질문은 기준을 선명하게 만드는 데 꼭 필요할 때만 한다.
  · 후반(마무리): 사용자가 찾은 기준을 짧게 요약하고 질문 없이 맺는다.
- 마무리 신호를 감지한다: 사용자가 '그래야겠다', '얘기해볼게', '알겠어', '고마워'처럼 행동 방향을 정했거나, '응', 'ㅇㅇ', '엉'처럼 짧은 동의만 이어지거나, '힘들다고 했잖아'처럼 같은 답을 되풀이하면
  → 새 반론이나 질문을 붙이지 말고, 지금까지 찾은 기준을 1~2문장으로 정리한 뒤, 오른쪽 X-ROOM에 포스트잇으로 남겨보라고 가볍게 권하며 끝낸다.
- 이전 답변에서 이미 한 말(같은 개념, 같은 제안, 같은 예시)을 반복하지 않는다. 새로 더할 내용이 없으면 2~3문장으로 짧게 답한다.
- 사용자가 합리적인 결론에 도달했다면 그것을 인정한다. 반박은 실제 논리 오류나 빠진 사실이 있을 때만 한다.

[입장 바꿔보기 요청]
사용자의 메시지가 '🔄 상대방 입장으로 뒤집어보기'로 시작하면:
- 사용자가 지금까지 말한 사실만 써서, 상대방 시점의 1인칭 고민으로 2~3문장 바꿔 쓴다. (> 인용문 형식)
- 그 시점에서도 지금까지와 같은 기준이 똑같이 적용되는지 한두 문장으로 짚는다.
- 상대의 속마음을 지어내지 않는다. 사용자가 말하지 않은 사정은 '~였을 수도 있다'는 가정으로만 쓴다."""

MODE_ROLES = {
    "empathy": """[이번 모드: 💛 감성 공감 모드]
- 비율: 감정 수용 약 70% + 내면 기준 탐색 약 30%. 개입 방식은 '해석(Interpretation)': 사용자의 감정을 구조화해서 비춰준다.
- 탐색 타겟은 '내면'이다: "나는 왜 서운한지(내 안의 결핍·욕구·바람)"를 향해 묻고 정리한다. 상대 조건을 바꿔보는 반례 제시는 팩폭 모드의 몫이므로 하지 않는다.
- 표면 감정 뒤의 욕구는 '~일 수도 있어' 같은 가설로만 말한다. 단정하지 않는다.
- 금지: 맹목적 편들기, 섣부른 행동 지시·해결책 나열, 훈계·평가. 따뜻하지만 사용자 편만 무조건 들지는 않는다. (컨트롤러 ①)
- 같은 호소가 반복되며 진전이 없으면 컨트롤러 ⑥에 따라 사용자의 의도를 묻는다.
- 제목은 '갈등 진단' 성격으로, 이번 답변에서 발견한 감정·바람의 핵심을 한 줄로 쓴다. 예: 서운함 뒤에 숨은 바람 살펴보기""",
    "fact": """[이번 모드: 🔥 팩트 폭격 모드]
- 비율: 상황·감정 인정 약 20%(한 문장) + 맹점·조건 대입 약 80%. 개입 방식은 '뜻밖의 전개(Unexpected Turn)': 놓친 사실, 이중 잣대, 조건을 바꿨을 때 달라지는 점을 보여준다.
- 탐색 타겟은 '외부'다: "상대 입장이나 조건을 바꾸면 어떤가(외부 반례·맹점)"를 향한다.
- 팩트 폭격은 무조건 반박하는 것이 아니다. 실제 논리 오류, 빠진 정보, 이중 잣대가 있을 때만 짚고, 사용자의 판단이 합리적이면 짧게 인정한다. 매 턴 새로운 반론을 만들어내지 않는다.
- 금지: 인신공격성 비난, 감정 자체를 부정하기, 단정적 위로, 기계적 양비론('둘 다 잘못했어').
- 사용자가 상처받았다고 호소하면 컨트롤러 ⑥에 따라 분석을 멈추고 이야기할지 묻는다.
- 제목은 '뜻밖의 전개' 성격으로, 이번 답변의 맹점이나 전환점을 한 줄로 쓴다. 예: 문제의 핵심은 만남보다 숨김""",
}

COMMON_FORMAT = """[규칙 우선순위 - 여러 컨트롤러가 동시에 해당하면 위에서부터 적용]
- 최우선 · 안전: 자해·자살 등 위기 신호가 보이면 모든 역할 설정과 컨트롤러를 내려놓고, 따뜻하게 안전을 먼저 확인하고 전문 도움(한국: 자살예방상담전화 109)을 안내한다.
- Tier 1 · 자율성 보호: ③ (결정 대행 거절과 호흡 조절이 다른 어떤 분석보다 먼저)
- Tier 2 · 사실 왜곡 차단: ① 아첨 방지 > ② 상황 구체화 > ④ 일반화 제어
- Tier 3 · 사고 확장·모드 유지: ⑤ 조건 바꿔보기 > ⑥ 모드 유지
- 한 답변에는 가장 중요한 1~2개만 적용한다. 해당하는 것이 없으면 억지로 적용하지 말고 자연스럽게 대화한다.

[공통 규칙]
- 반드시 한국어로 답한다. 사용자가 반말이면 부드러운 반말, 존댓말이면 존댓말로 맞춘다.
- 사용자가 실제로 말한 내용(상황, 인물, 감정)을 구체적으로 짚는다. 사용자가 말하지 않은 사실(상대의 속마음, 사정)을 지어내지 않는다.
- 본문은 2~5문장으로 간결하게 쓴다. 마지막을 질문으로 끝낼지는 [대화 흐름 규칙]에 따라 정한다.
- 이전 대화의 일부는 다른 모드에서 쓰였을 수 있다. 이전 말투와 상관없이 지금 모드의 역할과 경계만 지킨다.

[출력 형식 - 반드시 이 순서와 표기를 지킬 것]
제목: (이번 답변의 핵심 한 줄, 30자 이내, 따옴표·기호 없이)
규칙: (이번 답변에서 가장 우선 작동한 규칙 하나를 다음 중에서 그대로 고른다: Tier 1 · 자율성 보호 / Tier 2 · 아첨 방지 / Tier 2 · 상황 구체화 / Tier 2 · 일반화 제어 / Tier 3 · 조건 바꿔보기 / Tier 3 · 모드 유지 / 없음)
다른 시선: (지금과 반대 모드였다면 던졌을 핵심 질문 한 줄. 공감 모드라면 외부 조건·반례를 묻는 팩폭식 질문, 팩폭 모드라면 내면의 욕구를 묻는 공감식 질문)
---
(여기부터 본문)"""


def _render_controllers():
    blocks = []
    for c in CONTROLLERS:
        required = "\n".join("  · " + r for r in c["required"])
        prohibited = "\n".join("  · " + p for p in c["prohibited"])
        blocks.append(
            f"{c['name']}\n- 발동 조건: {c['trigger']}\n- 반드시 할 것:\n{required}\n- 절대 하지 말 것:\n{prohibited}"
        )
    return "\n\n".join(blocks)


def _render_examples():
    lines = []
    for user, reply in EXAMPLES:
        lines.append(f"사용자: {user}\n좋은 본문 예시: {reply}")
    return "\n\n".join(lines)


def build_system_prompt(mode_key):
    return "\n\n".join(
        [
            MODE_ROLES[mode_key],
            CORE_PRINCIPLES,
            "[컨트롤러 6가지 - 발동 조건에 해당하면 반드시 적용]\n\n" + _render_controllers(),
            FLOW_RULES,
            "[좋은 응답 예시 - 방향만 참고하고, 문장을 그대로 베끼지 말 것. 제목·규칙·다른 시선 줄은 생략된 예시다]\n\n" + _render_examples(),
            COMMON_FORMAT,
        ]
    )


def stage_note(user_turns):
    """대화 단계(초반/중반/후반)를 모델에게 알려줘서 단계별로 응답 전략을 바꾸게 한다."""
    if user_turns <= 2:
        stage = "초반(탐색)"
    elif user_turns <= 5:
        stage = "중반(정리)"
    else:
        stage = "후반(마무리를 고려)"
    return (
        f"\n\n[현재 대화 상태]\n- 이번이 사용자의 {user_turns}번째 발화이고, 단계는 {stage}이다. "
        "단, 마무리 신호가 보이면 단계와 상관없이 마무리한다."
    )


SYSTEM_PROMPTS = {key: build_system_prompt(key) for key in MODE_ROLES}


MODES = {
    "empathy": {
        "key": "empathy",
        "label": "감성 공감 모드 💛",
        "short": "공감",
        "emoji": "💛",
        "provider": "anthropic",
        "model": get_secret("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
    },
    "fact": {
        "key": "fact",
        "label": "팩트 폭격 모드 🔥",
        "short": "팩폭",
        "emoji": "🔥",
        "provider": "openai",
        # 기본값: gpt-5.6-sol (다른 모델을 쓰려면 secrets / 환경변수 OPENAI_MODEL 로 지정)
        "model": get_secret("OPENAI_MODEL", "gpt-5.6-sol"),
    },
}

# '입장 바꿔보기' 버튼이 보내는 메시지 (시스템 프롬프트의 [입장 바꿔보기 요청] 규칙과 짝)
MIRROR_PROMPT = "🔄 상대방 입장으로 뒤집어보기: 지금까지 내가 말한 고민을 상대방 입장에서 다시 보여줘."

# 모드별 포인트 컬러: 감성 공감 = 노랑(기본 톤) / 팩트 폭격 = 파랑
# on = 포인트 색 위에 올라가는 글자색
THEMES = {
    "empathy": {
        "accent": "#F2C45A", "soft": "#FBE8AE", "deep": "#8A5A00", "ring": "rgba(242,196,90,.35)",
        "on": "#2E2108", "border": "#E9B23C", "glow": "rgba(214,160,30,.75)",
    },
    "fact": {
        "accent": "#2F55F5", "soft": "#E8ECFF", "deep": "#2437B0", "ring": "rgba(47,85,245,.22)",
        "on": "#FFFFFF", "border": "#2F55F5", "glow": "rgba(47,85,245,.75)",
    },
}



# ─────────────────────────────────────────────
# 3. LLM 호출 (스트리밍)
# ─────────────────────────────────────────────
MAX_HISTORY = 20  # API로 보낼 최근 메시지 수 (비용/맥락 길이 관리)
MAX_TOKENS = 4000  # 모델이 내부 추론에 토큰을 쓰는 경우를 대비해 여유 있게 설정


# ─────────────────────────────────────────────
# 3. LLM 호출 (스트리밍)
# ─────────────────────────────────────────────
def stream_anthropic(cfg, system_prompt, history):
    import anthropic

    api_key = get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY를 찾을 수 없습니다. .streamlit/secrets.toml 또는 환경변수를 확인하세요.")

    client = anthropic.Anthropic(api_key=api_key)
    with client.messages.stream(
        model=cfg["model"],
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=history,
    ) as stream:
        for text in stream.text_stream:
            yield text

        # 텍스트가 하나도 없었다면 원인(stop_reason 등)을 알려준다
        final = stream.get_final_message()
        got_text = any(
            getattr(b, "type", "") == "text" and getattr(b, "text", "")
            for b in final.content
        )
        if not got_text:
            block_types = [getattr(b, "type", "?") for b in final.content]
            raise RuntimeError(
                f"모델이 텍스트를 반환하지 않았습니다 "
                f"(stop_reason={final.stop_reason}, blocks={block_types}, max_tokens={MAX_TOKENS})"
            )


def stream_openai(cfg, system_prompt, history):
    from openai import OpenAI

    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY를 찾을 수 없습니다. .streamlit/secrets.toml 또는 환경변수를 확인하세요.")

    client = OpenAI(api_key=api_key)
    stream = client.chat.completions.create(
        model=cfg["model"],
        messages=[{"role": "system", "content": system_prompt}] + history,
        stream=True,
    )
    got_text, finish = False, None
    for chunk in stream:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if choice.delta.content:
            got_text = True
            yield choice.delta.content
        if choice.finish_reason:
            finish = choice.finish_reason
    if not got_text:
        raise RuntimeError(f"모델이 텍스트를 반환하지 않았습니다 (finish_reason={finish})")


def stream_reply(cfg, history, user_turns):
    system_prompt = SYSTEM_PROMPTS[cfg["key"]] + stage_note(user_turns)
    if cfg["provider"] == "anthropic":
        return stream_anthropic(cfg, system_prompt, history)
    return stream_openai(cfg, system_prompt, history)


# ─────────────────────────────────────────────
# 4. 스타일 (CSS)
# ─────────────────────────────────────────────
FONT_IMPORTS = (
    # Fraunces: 'E-um' 같은 굵은 디스플레이 세리프 (영문 타이틀)
    # Noto Serif KR: 타이틀 속 한글('이음')을 Fraunces 굵기에 맞춰 받쳐주는 명조
    # Inter: 'Find Your Own Standard' 같은 깔끔한 그로테스크 산세리프 (영문 본문)
    "@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400..900"
    "&family=Inter:wght@300..700&family=Noto+Serif+KR:wght@700;900&display=swap');"
    # Pretendard: 한글 본문 / 채팅 말풍선 (영문은 Inter가 먼저 쓰인다)
    "@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');"
)

BASE_CSS = r"""
:root{
  --ink:#1F1A12; --muted:#7A6F58; --cream:#FBF4E6; --card:#FFFFFF; --line:#ECE3CF;
  --placeholder:#A89B80; --track:#E2DFD8; --idle-fg:#4A463F;
  --font-body:"Inter", "Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont,
              "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", sans-serif;
  --font-display:"Fraunces", "Noto Serif KR", Georgia, serif;
  color-scheme: light;
}
@media (prefers-reduced-motion: reduce){ *{ transition:none !important; } }

/* CSS 주입용 빈 컨테이너가 공간을 차지하지 않도록 */
div[data-testid="stElementContainer"]:has(.eum-css-anchor),
.element-container:has(.eum-css-anchor){ display:none !important; }

/* ── 전체: 크림 배경 + 왼쪽 노랑 / 오른쪽 파랑 글로우 ── */
html, body, .stApp{ font-family:var(--font-body); }
.stApp{
  color:var(--ink) !important;
  background:
    radial-gradient(36% 48% at 17% 64%, rgba(255,200,40,.50) 0%, rgba(255,214,90,.20) 45%, transparent 75%),
    radial-gradient(34% 48% at 79% 64%, rgba(40,90,245,.55) 0%, rgba(70,110,245,.22) 45%, transparent 75%),
    var(--cream) !important;
  background-attachment:fixed !important;
}
.stApp p, .stApp li, .stApp label, .stApp textarea, .stApp input, .stApp button{ font-family:inherit; }
header[data-testid="stHeader"]{ background:transparent !important; }
footer, [data-testid="stAppDeployButton"], .stDeployButton,
[data-testid="stMainMenu"], #MainMenu{ display:none !important; }
/* 코드·저장소가 보이지 않게: 툴바(Fork·GitHub·소스 보기), 상단 장식선, 호스팅 배지 숨김 */
[data-testid="stToolbar"], .stAppToolbar, [data-testid="stDecoration"],
[class*="viewerBadge"], [class*="_profileContainer"], [class*="_link_gzau3"]{ display:none !important; }
/* 전체 크기 5% 축소 (배경 글로우는 그대로, 내용만) */
.block-container{
  zoom:.95;
  max-width:1320px !important;
  padding-top:2.6rem !important; padding-bottom:3rem !important;
  padding-left:2.5rem !important; padding-right:2.5rem !important;
}
@media (max-width:640px){
  .block-container{ padding-left:1rem !important; padding-right:1rem !important; padding-top:2rem !important; }
}

/* ── 상단 타이틀 (이음 E-um / Mind Prism) ── */
.eum-hero{ text-align:center; margin:.5rem 0 2.4rem; color:var(--ink); }
.eum-hero__title{
  font-family:var(--font-display); font-weight:800; font-size:clamp(2.8rem, 5.4vw, 4.6rem);
  font-variation-settings:"opsz" 48, "SOFT" 0; line-height:1.1; letter-spacing:-.015em; white-space:nowrap;
}
.eum-hero__title .ko{ font-family:"Noto Serif KR", serif; font-weight:900; letter-spacing:-.04em; }
.eum-hero__title .en{ margin-left:.22em; }
.eum-hero__sub{
  margin-top:1rem; font-weight:500; font-size:clamp(1.05rem, 1.9vw, 1.55rem);
  line-height:1.4; letter-spacing:-.01em; word-break:keep-all;
}

/* ── 이음 → Mind Prism: 러브레터가 점선 궤적을 따라 날아가는 연출 ── */
div[data-testid="stElementContainer"]:has(.eum-letter){ margin-bottom:-1rem; z-index:2; }
.eum-letter{ position:relative; height:0; pointer-events:none; }
.eum-letter__stage{ position:absolute; top:-6px; left:38.6%; width:15%; height:120px; }
.eum-letter__path{ position:absolute; inset:0; width:100%; height:100%; overflow:visible; }
.eum-letter__path path{
  fill:none; stroke:url(#eumLetterGrad); stroke-width:2; stroke-linecap:round;
  stroke-dasharray:2 9; vector-effect:non-scaling-stroke; opacity:.75;
}
.eum-letter__dot{ position:absolute; top:70px; width:9px; height:9px; margin:-4.5px 0 0 -4.5px; border-radius:50%; }
.eum-letter__dot--from{ left:0; background:#E9B23C; box-shadow:0 0 0 5px rgba(233,178,60,.18); }
.eum-letter__dot--to{ left:100%; background:#2F55F5; box-shadow:0 0 0 5px rgba(47,85,245,.18); }
/* 가로는 일정하게, 세로는 올라갈 땐 감속·내려올 땐 가속 → 점선과 같은 포물선 */
.eum-letter__fly{ position:absolute; left:0; top:70px; animation:eumLetterX 5.2s linear infinite; }
.eum-letter__lift{ animation:eumLetterY 5.2s infinite; }
.eum-letter__env{
  display:block; font-size:2rem; line-height:1; transform:translate(-50%,-50%);
  filter:drop-shadow(0 8px 10px rgba(120,60,20,.25)); animation:eumLetterTilt 5.2s ease-in-out infinite;
}
.eum-letter__pop{
  position:absolute; left:100%; top:70px; font-size:1.05rem; color:#F06B8B;
  transform:translate(-50%,-50%) scale(0); animation:eumLetterPop 5.2s ease-out infinite;
}
@keyframes eumLetterX{ 0%{ left:0; opacity:0; } 8%{ opacity:1; } 88%{ opacity:1; } 100%{ left:100%; opacity:0; } }
@keyframes eumLetterY{
  0%{ transform:translateY(0); animation-timing-function:cubic-bezier(.33,.66,.66,1); }
  50%{ transform:translateY(-54px); animation-timing-function:cubic-bezier(.33,0,.66,.33); }
  100%{ transform:translateY(0); }
}
@keyframes eumLetterTilt{ 0%{ rotate:-16deg; } 50%{ rotate:0deg; } 100%{ rotate:16deg; } }
@keyframes eumLetterPop{
  0%, 90%{ transform:translate(-50%,-50%) scale(0); opacity:0; }
  95%{ transform:translate(-50%,-150%) scale(1.15); opacity:1; }
  100%{ transform:translate(-50%,-210%) scale(.9); opacity:0; }
}
@media (prefers-reduced-motion: reduce){
  .eum-letter__fly, .eum-letter__lift, .eum-letter__env, .eum-letter__pop{ animation:none !important; }
  .eum-letter__fly{ left:50%; }
  .eum-letter__lift{ transform:translateY(-54px); }
}
@media (max-width:640px){ .eum-letter{ display:none; } }

/* ── 카드 공통: 반투명 유리 ── */
.st-key-eum_card, .st-key-xroom_card{
  border-radius:28px; padding:2rem 2rem 1.6rem !important;
  border:1px solid rgba(255,255,255,.85); backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px);
}
.st-key-eum_card{
  background:rgba(255,251,242,.72);
  box-shadow:0 30px 70px -30px rgba(140,100,10,.35);
  gap:1.1rem !important;
}
.st-key-xroom_card{
  background:linear-gradient(160deg, rgba(160,182,250,.78), rgba(118,146,246,.72));
  border-color:rgba(255,255,255,.55);
  box-shadow:0 0 110px 20px rgba(47,85,245,.35);
}
@media (max-width:640px){
  .st-key-eum_card, .st-key-xroom_card{ padding:1.2rem 1rem 1rem !important; border-radius:22px; }
}

/* ── 모드 선택: 하나의 캡슐 트랙 안에서 선택된 쪽만 떠오르는 세그먼트 ── */
.st-key-eum_card [data-testid="stElementContainer"]:has([data-testid="stRadio"]),
.st-key-eum_card [data-testid="stRadio"]{ margin:0 !important; width:100% !important; }
[data-testid="stRadioGroup"]{
  display:flex !important; flex-direction:row !important; flex-wrap:nowrap !important; gap:0 !important;
  width:100%; padding:7px; border-radius:999px; background:var(--track);
  box-shadow:inset 0 2px 6px rgba(0,0,0,.10);
}
[data-testid="stRadioGroup"] > *{ flex:1 1 0; min-width:0; margin:0 !important; }
[data-testid="stRadioOption"]{
  box-sizing:border-box; width:100%; min-height:3.4rem; margin:0 !important; padding:.8rem 1rem !important;
  display:flex !important; align-items:center; justify-content:center; text-align:center; cursor:pointer;
  background:transparent; color:var(--idle-fg); border-radius:999px;
  transition:background-color .25s ease, color .25s ease, box-shadow .25s ease, transform .15s ease;
  -webkit-tap-highlight-color:transparent;
}
/* 작은 동그라미 숨김: 글자(stMarkdownContainer)의 형제 요소 */
[data-testid="stRadioOption"] :has(> [data-testid="stMarkdownContainer"]){ margin:0 !important; gap:0 !important; }
[data-testid="stRadioOption"] :has(> [data-testid="stMarkdownContainer"]) > :not([data-testid="stMarkdownContainer"]){
  display:none !important;
}
[data-testid="stRadioOption"] p{
  margin:0; font-size:1.12rem; font-weight:600; line-height:1.3;
  text-align:center; word-break:keep-all; color:inherit !important;
}
[data-testid="stRadioOption"]:hover{ background:rgba(255,255,255,.45); }
[data-testid="stRadioOption"][data-selected="true"]{
  background:var(--accent); color:var(--on-accent);
  box-shadow:0 10px 20px -10px var(--accent-glow), inset 0 1px 0 rgba(255,255,255,.45);
}
[data-testid="stRadioOption"]:active{ transform:scale(.98); }
[data-testid="stRadioOption"]:has(input:focus-visible){ outline:3px solid var(--ink); outline-offset:2px; }
@media (max-width:640px){
  [data-testid="stRadioOption"]{ min-height:3rem; padding:.7rem .5rem !important; }
  [data-testid="stRadioOption"] p{ font-size:.98rem; }
}
.eum-divider{ height:1px; background:var(--line); margin:.6rem 0 0; }

/* ── 빈 화면 안내 ── */
.eum-empty{
  margin:.4rem 0 0; padding:1.3rem 1.4rem; border-radius:18px;
  background:rgba(255,255,255,.6); border:1px dashed #E6D49A;
}
.eum-empty p{ margin:0 0 .6rem; font-weight:600; font-size:.98rem; line-height:1.7; color:var(--ink); word-break:keep-all; }
.eum-empty ul{ margin:0; padding-left:1.2rem; color:var(--muted); font-size:.93rem; line-height:2; }

/* ── 채팅 말풍선 ── */
[data-testid="stChatMessage"]{
  width:100%; box-sizing:border-box;
  background:transparent !important; padding:.55rem 0 !important; gap:.75rem; align-items:flex-start;
}
/* 사용자: 오른쪽 정렬, 아바타 숨김 */
[data-testid="stChatMessageAvatarUser"], [data-testid="chatAvatarIcon-user"]{ display:none !important; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]){ flex-direction:row-reverse; }

/* 봇 아바타: 공감 모드 = F봇(노랑), 팩폭 모드 = T봇(파랑) */
[data-testid="stChatMessageAvatarAssistant"], [data-testid="chatAvatarIcon-assistant"]{
  display:flex !important; align-items:center; justify-content:center;
  width:2.5rem !important; height:2.5rem !important; border-radius:50% !important;
  background:#FFF7E0 !important; border:1px solid #F0E3BC; box-shadow:0 6px 14px -8px rgba(120,90,20,.5);
}
[data-testid="stChatMessageAvatarAssistant"] > *, [data-testid="chatAvatarIcon-assistant"] > *{ display:none !important; }
[data-testid="stChatMessageAvatarAssistant"]::after, [data-testid="chatAvatarIcon-assistant"]::after{
  content:"F봇"; font-weight:700; font-size:.78rem; letter-spacing:-.02em; color:#5A3E00;
}
[data-testid="stChatMessage"]:has(.eum-who--fact) [data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessage"]:has(.eum-who--fact) [data-testid="chatAvatarIcon-assistant"]{
  background:#E8ECFF !important; border-color:#C9D3FF; box-shadow:0 6px 14px -8px rgba(47,85,245,.55);
}
[data-testid="stChatMessage"]:has(.eum-who--fact) [data-testid="stChatMessageAvatarAssistant"]::after,
[data-testid="stChatMessage"]:has(.eum-who--fact) [data-testid="chatAvatarIcon-assistant"]::after{
  content:"T봇"; color:#1E2E99;
}
.eum-who{ display:none; }

/* 말풍선 공통 (AI 기본값) */
[data-testid="stChatMessageContent"]{
  flex:0 1 auto !important; width:fit-content; max-width:min(calc(100% - 3.2rem), 32rem);
  padding:1rem 1.25rem; line-height:1.8; word-break:keep-all; overflow-wrap:anywhere;
  background:var(--card) !important; color:var(--ink) !important;
  border:none; border-radius:18px; box-shadow:0 14px 28px -16px rgba(60,45,10,.35);
}
[data-testid="stChatMessageContent"] p{ margin:0 0 .8rem; font-size:.98rem; line-height:1.8; }
[data-testid="stChatMessageContent"] p:last-child{ margin-bottom:0; }
/* Streamlit 기본값(margin-bottom:-16px)이 아래 여백을 잡아먹어 글자가 아래로 치우쳐 보이던 문제 */
[data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"]{ margin-bottom:0 !important; }
[data-testid="stChatMessageContent"] [data-testid="stVerticalBlock"]{ gap:.35rem !important; }

/* 사용자 말풍선: 포인트 색 */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"],
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"]{
  max-width:80%; padding:.95rem 1.3rem; line-height:1.7;
  background:var(--accent) !important; border-radius:18px;
  box-shadow:0 14px 26px -14px var(--accent-glow);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] *,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] *{
  color:var(--on-accent) !important; line-height:1.7; font-weight:500;
}

/* 다른 모드의 시선 보기 (접힘) */
.eum-lens{ margin-top:.85rem; padding-top:.6rem; border-top:1px dashed var(--line); }
.eum-lens summary{ cursor:pointer; list-style:none; font-size:.82rem; font-weight:600; color:var(--muted); }
.eum-lens summary::-webkit-details-marker{ display:none; }
.eum-lens summary:hover{ color:var(--ink); }
.eum-lens p{ margin:.45rem 0 0 !important; font-size:.88rem !important; line-height:1.7 !important; }

/* AI 답변 위의 한 줄 제목: 캡슐형 칩 (모드별 색 고정) */
.eum-banner{
  display:inline-block; padding:.35rem .9rem; margin-bottom:.75rem; border-radius:999px;
  font-weight:700; font-size:.92rem; line-height:1.5; word-break:keep-all;
}
.eum-banner--empathy{ background:#FBE8AE; color:#3B2A00; }
.eum-banner--fact{ background:#DCE4FF; color:#1E2E99; }

/* 에러 / 알림 */
[data-testid="stAlert"]{ border-radius:14px; border:none; }

/* ── 입력창 (카드 안에 인라인) ── */
.st-key-eum_card [data-testid="stChatInput"]{
  background:#fff !important; border:1px solid #E6DFCF !important; border-radius:999px !important;
  box-shadow:0 8px 20px -14px rgba(60,45,10,.4); transition:border-color .15s, box-shadow .15s;
}
.st-key-eum_card [data-testid="stChatInput"] > div{
  background:transparent !important; border:none !important; box-shadow:none !important; border-radius:999px !important;
}
.st-key-eum_card [data-testid="stChatInput"]:focus-within{
  border-color:var(--accent-border) !important; box-shadow:0 0 0 3px var(--accent-ring);
}
.st-key-eum_card [data-testid="stChatInput"] textarea{
  color:var(--ink) !important; font-size:1rem; line-height:1.6; padding:.85rem 1.3rem !important;
}
.st-key-eum_card [data-testid="stChatInput"] textarea::placeholder{ color:var(--placeholder) !important; }
@media (max-width:640px){
  .st-key-eum_card [data-testid="stChatInput"] textarea{ font-size:.9rem; padding:.8rem .9rem !important; }
}
.st-key-eum_card [data-testid="stChatInput"] button{
  background:#F1EEE7 !important; color:#6B655A !important; border:1px solid #E2DDD2 !important;
  border-radius:50% !important; transition:background-color .15s;
}
.st-key-eum_card [data-testid="stChatInput"] button svg{ fill:currentColor !important; color:inherit !important; }
.st-key-eum_card [data-testid="stChatInput"] button:not(:disabled):hover{
  background:var(--accent) !important; color:var(--on-accent) !important;
}

/* 보조 텍스트 버튼 (대화 초기화 / 포스트잇 떼기) */
.st-key-eum_actions{ margin-top:-.4rem; }
.st-key-btn_mirror button p{ font-size:.85rem; font-weight:600; color:var(--accent-deep) !important; }
.st-key-btn_reset, .st-key-btn_clear_notes{ align-items:flex-end; }
.st-key-btn_reset [data-testid="stButton"], .st-key-btn_clear_notes [data-testid="stButton"]{ display:flex; justify-content:flex-end; }
.st-key-btn_reset button, .st-key-btn_clear_notes button{ min-height:0 !important; padding:.1rem .3rem !important; }
.st-key-btn_reset button p{ font-size:.82rem; color:var(--muted) !important; }
.st-key-btn_clear_notes button p{ font-size:.82rem; color:#1C2557 !important; }

/* ── X-ROOM: 속마음 문자 종이 ── */
.st-key-xr_paper{
  background:#fff; border-radius:16px; overflow:hidden; gap:0 !important;
  box-shadow:0 24px 44px -22px rgba(20,30,100,.55);
}
.xr-head{ background:#F6D774; padding:.7rem 1.4rem 1.15rem; }
.xr-handle{ display:block; width:68px; height:7px; border-radius:7px; background:rgba(90,70,20,.18); margin:0 auto .95rem; }
.xr-head__title{ font-weight:800; font-size:1.18rem; color:var(--ink); word-break:keep-all; }
.st-key-xr_paper [data-testid="stForm"]{ padding:1.1rem 1.4rem 1.4rem !important; border:none !important; }
.st-key-xr_paper [data-testid="stWidgetLabel"] p{ font-size:.86rem; font-weight:600; color:var(--ink); }
.st-key-xr_paper [data-testid="stTextAreaRootElement"]{
  background:#F1F1F1 !important; border:1px solid #E6E6E6 !important; border-radius:10px !important;
}
.st-key-xr_paper textarea{ background:transparent !important; color:var(--ink) !important; font-size:.9rem; line-height:1.6; }
.st-key-xr_paper textarea::placeholder{ color:#A8A8A8 !important; }
.st-key-xr_final [data-testid="stTextAreaRootElement"]{
  background:#FFEE9A !important; border-color:#FFE27A !important; box-shadow:0 12px 22px -14px rgba(120,95,0,.55);
}
.st-key-xr_final textarea::placeholder{ color:#A08A3A !important; }
.st-key-xr_paper [data-testid="stFormSubmitButton"] button{
  min-height:2.9rem; border:none; border-radius:999px; background:var(--ink) !important;
  transition:background-color .2s, transform .15s;
}
.st-key-xr_paper [data-testid="stFormSubmitButton"] button p{ color:#fff !important; font-weight:700; }
.st-key-xr_paper [data-testid="stFormSubmitButton"] button:hover{ background:#2F55F5 !important; transform:translateY(-1px); }

/* ── X-ROOM: 작성한 포스트잇 보드 ── */
.xr-notes__label{ font-weight:700; font-size:.9rem; color:#141A40; margin:.15rem 0 .9rem; }
.xr-grid{
  display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px;
  max-height:520px; overflow-y:auto; padding:2px 4px 10px 2px;
}
.xr-note{
  aspect-ratio:1; border-radius:6px; padding:.65rem .7rem; overflow:hidden;
  display:flex; flex-direction:column; gap:.3rem;
  box-shadow:0 12px 20px -12px rgba(20,30,100,.55);
  font-size:.76rem; line-height:1.45; color:var(--ink); word-break:keep-all; overflow-wrap:anywhere;
}
.xr-note--yellow{ background:#FFEE9A; }
.xr-note--pink{ background:#F9C8CE; }
.xr-note--blue{ background:#BEDBFF; }
.xr-note--empty{ opacity:.6; }
.xr-note__topic{ font-weight:700; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.xr-note__body{ display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
.xr-notes__hint{ margin:.9rem 0 0; font-size:.8rem; line-height:1.6; color:#1C2557; word-break:keep-all; }
"""


def inject_css(mode_key):
    t = THEMES[mode_key]
    root = (
        ":root{"
        f"--accent:{t['accent']};--accent-soft:{t['soft']};--accent-deep:{t['deep']};--accent-ring:{t['ring']};"
        f"--on-accent:{t['on']};--accent-border:{t['border']};--accent-glow:{t['glow']};"
        "}"
    )
    st.markdown(
        f"<style>{FONT_IMPORTS}{root}{BASE_CSS}</style><div class='eum-css-anchor'></div>",
        unsafe_allow_html=True,
    )


def other_mode(mode_key):
    return "fact" if mode_key == "empathy" else "empathy"


# 모델 출력 머리말: '제목: …' / '규칙: …' / '다른 시선: …' 다음 '---' 뒤가 본문
HEADER_RE = re.compile(r"^[\s*#>\[]*(제목|규칙|다른 시선)[\]*\s]*[:：]\s*(.*?)[\s*]*$")
SEP_RE = re.compile(r"^\s*-{3,}\s*$")


def parse_reply(text):
    """모델 출력을 (머리말 dict, 본문)으로 나눈다.
    첫 줄을 무조건 제목으로 보지 않고 '제목:' 같은 표시가 붙은 줄만 골라내므로,
    모델이 형식을 어겨도 본문과 제목이 뒤바뀌지 않는다."""
    meta, body_lines = {}, []
    for line in text.splitlines():
        m = HEADER_RE.match(line)
        if m and m.group(1) not in meta:
            meta[m.group(1)] = m.group(2).strip("*\"'“” ")
        elif SEP_RE.match(line) and not any(l.strip() for l in body_lines):
            continue
        else:
            body_lines.append(line)
    return meta, "\n".join(body_lines).strip()


def render_head(container, mode_key, meta):
    """AI 말풍선 윗부분: 한 줄 제목. (모드·규칙은 배지로 드러내지 않고 말투로 느껴지게 한다)
    eum-who는 화면에 보이지 않고, 아바타를 F봇/T봇으로 바꾸는 표시로만 쓴다."""
    head = f"<span class='eum-who eum-who--{mode_key}'></span>"
    if meta.get("제목"):
        head += f"<div class='eum-banner eum-banner--{mode_key}'>{html.escape(meta['제목'])}</div>"
    container.markdown(head, unsafe_allow_html=True)


def render_lens(container, mode_key, meta):
    """반대 모드였다면 던졌을 질문을 접어 두는 '다른 모드의 시선 보기'."""
    lens = meta.get("다른 시선")
    if not lens:
        return
    o = MODES[other_mode(mode_key)]
    container.markdown(
        f"<details class='eum-lens'><summary>🔍 다른 모드의 시선 보기</summary>"
        f"<p><b>{o['emoji']} {o['short']}</b> {html.escape(lens)}</p></details>",
        unsafe_allow_html=True,
    )


def render_assistant(msg):
    mk = msg.get("mode_key", "empathy")
    meta = msg.get("meta") or {"제목": msg.get("banner", "")}
    render_head(st, mk, meta)
    st.markdown(msg["content"])
    render_lens(st, mk, meta)


# 포스트잇 색 순서 (시안의 보드 배치: 노랑 → 분홍 → 분홍 → 파랑 → 파랑)
NOTE_COLORS = ("yellow", "pink", "pink", "blue", "blue")


def render_notes_html(notes):
    """X-ROOM 오른쪽의 포스트잇 보드 HTML. 비어 있으면 옅은 빈 포스트잇을 보여준다."""
    if not notes:
        cells = "".join(f"<div class='xr-note xr-note--{c} xr-note--empty'></div>" for c in NOTE_COLORS)
        hint = "<p class='xr-notes__hint'>대화를 마치고 왼쪽 문자를 채워 붙여보세요.</p>"
        return f"<div class='xr-grid'>{cells}</div>{hint}"

    cells = []
    for i, n in enumerate(notes):
        color = NOTE_COLORS[i % len(NOTE_COLORS)]
        parts = []
        if n["topic"]:
            parts.append(f"<div class='xr-note__topic'>{html.escape(n['topic'])}</div>")
        body = n["final"] or n["rule"]  # 칸이 작아 본문은 하나만, 전체 내용은 마우스를 올리면 보인다
        if body:
            parts.append(f"<div class='xr-note__body'>{html.escape(body)}</div>")
        full = html.escape(" / ".join(v for v in (n["topic"], n["rule"], n["final"]) if v), quote=True)
        cells.append(f"<div class='xr-note xr-note--{color}' title=\"{full}\">{''.join(parts)}</div>")
    return f"<div class='xr-grid'>{''.join(cells)}</div>"


# ─────────────────────────────────────────────
# 5. 상태 / 스타일 적용
# ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "notes" not in st.session_state:
    st.session_state.notes = []

# 라디오 위젯의 현재 선택값을 먼저 읽어서, 첫 렌더부터 모드 색상으로 칠한다
current_mode = st.session_state.get("mode", "empathy")
if current_mode not in MODES:
    current_mode = "empathy"
inject_css(current_mode)


def require_password():
    """APP_PASSWORD가 설정돼 있으면 비밀번호를 아는 사람만 들어올 수 있게 한다.
    (배포 시 내 API 키가 무제한으로 쓰이지 않도록. 설정하지 않으면 누구나 바로 사용)"""
    password = get_secret("APP_PASSWORD")
    if not password or st.session_state.get("authed"):
        return
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown(
            "<div class='eum-hero'><div class='eum-hero__title'><span class='ko'>이음</span><span class='en'>E-um</span></div>"
            "<div class='eum-hero__sub'>Find Your Own Standard</div></div>",
            unsafe_allow_html=True,
        )
        with st.form("login", border=False):
            entered = st.text_input("입장 비밀번호", type="password", placeholder="전달받은 비밀번호를 입력해 주세요")
            if st.form_submit_button("입장하기", width="stretch"):
                if hmac.compare_digest(entered.encode(), password.encode()):
                    st.session_state.authed = True
                    st.rerun()
                st.error("비밀번호가 맞지 않아요.")
    st.stop()


require_password()

st.markdown(
    "<div class='eum-letter' aria-hidden='true'><div class='eum-letter__stage'>"
    "<svg class='eum-letter__path' viewBox='0 0 100 120' preserveAspectRatio='none'>"
    "<defs><linearGradient id='eumLetterGrad' x1='0' x2='1' y1='0' y2='0'>"
    "<stop offset='0' stop-color='#E9B23C'/><stop offset='1' stop-color='#2F55F5'/></linearGradient></defs>"
    "<path d='M0,70 C30,-2 70,-2 100,70'/></svg>"
    "<span class='eum-letter__dot eum-letter__dot--from'></span><span class='eum-letter__dot eum-letter__dot--to'></span>"
    "<div class='eum-letter__fly'><div class='eum-letter__lift'><span class='eum-letter__env'>💌</span></div></div>"
    "<span class='eum-letter__pop'>♥</span>"
    "</div></div>",
    unsafe_allow_html=True,
)

left, right = st.columns(2, gap="large")


# ─────────────────────────────────────────────
# 6. 왼쪽: 이음(E-um) 채팅
# ─────────────────────────────────────────────
with left:
    st.markdown(
        "<div class='eum-hero'><div class='eum-hero__title'><span class='ko'>이음</span><span class='en'>E-um</span></div>"
        "<div class='eum-hero__sub'>당신의 연애, 어떤 기준으로 이어가고 있나요?</div></div>",
        unsafe_allow_html=True,
    )

    with st.container(key="eum_card"):
        mode_key = st.radio(
            "어떤 대화를 원하시나요?",
            list(MODES.keys()),
            format_func=lambda k: MODES[k]["label"],
            key="mode",
            horizontal=True,
            label_visibility="collapsed",
        )
        cfg = MODES[mode_key]
        st.markdown("<div class='eum-divider'></div>", unsafe_allow_html=True)

        chat_box = st.container(height=360, border=False, key="eum_chat")
        visible = [m for m in st.session_state.messages if m["content"].strip()]
        with chat_box:
            if not visible:
                st.markdown(
                    "<div class='eum-empty'><p>어떤 이야기든 괜찮아요. 이렇게 시작해 볼 수 있어요.</p><ul>"
                    "<li>연락이 뜸해져서 자꾸 마음이 쓰여요</li>"
                    "<li>애인의 오랜 친구가 신경 쓰여요</li>"
                    "<li>이 관계를 이어가도 될지 모르겠어요</li>"
                    "</ul></div>",
                    unsafe_allow_html=True,
                )

            # 이전 대화 기록 출력 (당시 모드의 배지·제목까지 복원)
            for m in visible:
                if m["role"] == "assistant":
                    with st.chat_message("assistant"):
                        render_assistant(m)
                else:
                    with st.chat_message("user"):
                        st.markdown(m["content"])

        prompt = st.chat_input("연애 고민을 편하게 이야기해 주세요")

        if visible:
            with st.container(horizontal=True, horizontal_alignment="distribute", key="eum_actions"):
                if st.button("🔄 상대방 입장으로 뒤집어보기", type="tertiary", key="btn_mirror"):
                    prompt = MIRROR_PROMPT
                if st.button("대화 초기화", type="tertiary", key="btn_reset"):
                    st.session_state.messages = []
                    st.rerun()


# ─────────────────────────────────────────────
# 7. 오른쪽: Mind Prism · 기억과 기준의 방 X-ROOM
# ─────────────────────────────────────────────
with right:
    st.markdown(
        "<div class='eum-hero xr-hero'><div class='eum-hero__title'>Mind Prism</div>"
        "<div class='eum-hero__sub'>기억과 기준의 방 X-ROOM</div></div>",
        unsafe_allow_html=True,
    )

    with st.container(key="xroom_card"):
        form_col, notes_col = st.columns([1.2, 1], gap="medium")

        with form_col:
            with st.container(key="xr_paper"):
                st.markdown(
                    "<div class='xr-head'><span class='xr-handle'></span>"
                    "<div class='xr-head__title'>오늘 밤, 당신의 속마음 문자</div></div>",
                    unsafe_allow_html=True,
                )
                with st.form("xr_form", clear_on_submit=True, border=False):
                    topic = st.text_area(
                        "어떤 고민에 대한 기록인가요?", key="xr_topic", height=80,
                        placeholder="예) 연락 문제로 자꾸 서운해지는 마음",
                    )
                    rule = st.text_area(
                        "오늘 대화로 찾은 나의 핵심 연애 기준은?", key="xr_rule", height=80,
                        placeholder="예) 바쁜 건 괜찮지만, 미리 말해주는 건 중요해",
                    )
                    final = st.text_area(
                        "최종 생각 정리 포스트잇", key="xr_final", height=130,
                        placeholder="결론은 스스로 내려요. 지금의 생각을 적어보세요.",
                    )
                    submitted = st.form_submit_button("📌 포스트잇 붙이기", width="stretch")

                if submitted:
                    note = {"topic": topic.strip(), "rule": rule.strip(), "final": final.strip()}
                    if any(note.values()):
                        st.session_state.notes.append(note)
                    else:
                        st.toast("한 칸이라도 적어야 포스트잇을 붙일 수 있어요.")

        with notes_col:
            st.markdown(
                "<div class='xr-notes__label'>작성한 정리 포스트잇</div>"
                + render_notes_html(st.session_state.notes),
                unsafe_allow_html=True,
            )
            if st.session_state.notes and st.button("포스트잇 모두 떼기", type="tertiary", key="btn_clear_notes"):
                st.session_state.notes = []
                st.rerun()


# ─────────────────────────────────────────────
# 8. 사용자 입력 → 실제 LLM 응답 (왼쪽 채팅창 안에 표시)
# ─────────────────────────────────────────────
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with chat_box:
        with st.chat_message("user"):
            st.markdown(prompt)

    # API에는 role/content만 보낸다 (최근 MAX_HISTORY개, 빈 메시지 제외)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[-MAX_HISTORY:]
        if m["content"].strip()
    ]
    # Anthropic API는 첫 메시지가 user여야 하므로 보정
    while history and history[0]["role"] != "user":
        history.pop(0)
    user_turns = sum(1 for m in st.session_state.messages if m["role"] == "user")

    with chat_box, st.chat_message("assistant"):
        head_box = st.empty()
        body_box = st.empty()
        lens_box = st.empty()
        render_head(head_box, mode_key, {})  # 첫 토큰 전부터 아바타를 F봇/T봇으로

        buffer, meta, body = "", {}, ""
        try:
            with st.spinner("생각을 정리하는 중..."):
                gen = stream_reply(cfg, history, user_turns)
                first_chunk = next(gen, None)  # 첫 토큰이 올 때까지 스피너 표시

            def all_chunks():
                if first_chunk:
                    yield first_chunk
                yield from gen

            head_shown = False
            for chunk in all_chunks():
                buffer += chunk
                meta, body = parse_reply(buffer)
                if not body:
                    continue  # 머리말(제목·규칙·다른 시선)을 받는 중
                if not head_shown:
                    render_head(head_box, mode_key, meta)
                    head_shown = True
                body_box.markdown(body + "▌")

            meta, body = parse_reply(buffer)
            if not body:
                raise RuntimeError("모델이 빈 응답을 반환했습니다.")
            render_head(head_box, mode_key, meta)
            body_box.markdown(body)
            render_lens(lens_box, mode_key, meta)

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": body,
                    "meta": meta,
                    "mode_key": mode_key,
                    "model": cfg["model"],
                }
            )
        except Exception as e:
            # 실패 시 방금 넣은 user 메시지를 제거해 role 순서가 꼬이지 않게 한다
            st.session_state.messages.pop()
            head_box.empty()
            body_box.error(f"응답을 가져오지 못했습니다: {e}")
        else:
            st.rerun()  # 대화 초기화 버튼 등 화면을 최신 상태로
