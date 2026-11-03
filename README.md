# 이음 (E-um) — Find Your Own Standard

연애 고민을 '감성 공감 모드 💛' / '팩트 폭격 모드 🔥'로 나누어 대화하고,
오른쪽 X-ROOM에서 스스로 찾은 연애 기준을 포스트잇으로 정리하는 Streamlit 앱입니다.

## 내 컴퓨터에서 실행

```bash
pip install -r requirements.txt
cp secrets.toml.example .streamlit/secrets.toml   # 열어서 API 키 입력
streamlit run app.py
```

## 다른 사람도 쓸 수 있게 배포하기 (Streamlit Community Cloud, 무료)

1. GitHub에 새 저장소를 만들고 이 폴더(`eum-app`)의 파일을 올립니다.
   `.gitignore` 덕분에 `.streamlit/secrets.toml`(API 키)은 올라가지 않아요.
2. https://share.streamlit.io 에 GitHub 계정으로 로그인 → **Create app**.
3. 저장소 / 브랜치(`main`) / Main file path(`app.py`)를 고릅니다.
4. **Advanced settings → Secrets** 에 `secrets.toml.example` 내용을 붙여넣고 실제 키로 바꿉니다.
5. **Deploy** → 생성된 `https://<이름>.streamlit.app` 링크를 공유하면 끝.

### 공유 전에 알아둘 것
- 모든 사용자의 대화가 **배포한 사람의 API 키**로 처리되고 비용도 그 계정에 청구됩니다.
  `APP_PASSWORD`를 설정하면 비밀번호를 아는 사람만 들어올 수 있어요.
- Anthropic / OpenAI 콘솔에서 월 사용 한도(spending limit)를 걸어두는 것을 권장합니다.
- 대화와 포스트잇은 각 사용자 브라우저 세션에만 있고, 새로고침하면 사라집니다.
  서버나 다른 사용자에게 저장·공유되지 않아요.
- 비밀번호나 키를 바꾸려면 Streamlit Cloud의 앱 Settings → Secrets 에서 수정하면 바로 반영됩니다.
