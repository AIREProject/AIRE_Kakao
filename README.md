# AIRE KakaoTalk Bot

Kakao i Open Builder의 SkillPayload를 기존 AIRE Backend의 모바일 Chat 요청으로 변환하는 독립
어댑터 서비스입니다. `AIRE_SERVER`, `AIRE_Discord`, Unreal과 Web 코드를 수정하지 않습니다.

```text
KakaoTalk Channel
  -> POST /kakao/skill
  -> AIRE_Kakao
  -> POST https://traip.mtvs2026.work/api/v1/integrations/kakao/chat
  -> MAKO SkillResponse
```

각 채널 사용자는 `bot.id + botUserKey`에서 파생된 독립 Backend Profile을 사용합니다. Profile마다
`demo-slot-1 / mako / kakao` scope가 고정되며 게임·웹의 `AIRE_OPEN` 기억과 공유하지 않습니다.
`bot.id`와 `user.id/type`은 Backend 요청까지만 보존되고, Backend는 HMAC 파생 ID만 저장합니다.
`user.type`은 `botUserKey`만 허용합니다.
일반 요청은 4초 안에
직접 응답하고, AI 챗봇 Callback 권한이 활성화된 요청은 `useCallback=true`를 먼저 반환한 뒤
1회용 HTTPS Callback URL로 최종 응답을 보냅니다.

## 환경변수

`.env.example`을 `.env`로 복사하고 `KAKAO_SKILL_SECRET`에 충분히 긴 무작위 값을 넣습니다.
Backend가 발급한 `KAKAO_ADAPTER_TOKEN`도 반드시 설정해야 합니다. 미설정 시 Skill 요청은
503으로 거부됩니다.
비밀값은 저장소에 커밋하지 않습니다.

## 카카오 챗봇 관리자센터

1. `스킬`에서 `MAKO Chat`을 생성합니다.
2. URL을 `https://<AIRE_Kakao 공개주소>/kakao/skill`로 설정합니다.
3. Header `X-Kakao-Skill-Secret`에 배포 환경과 같은 비밀값을 넣습니다.
4. 모든 자유 발화를 받을 폴백 블록에 스킬을 연결하고 응답을 스킬 데이터로 설정합니다.
5. 봇 테스트 후 개발 채널에 배포합니다.
6. LLM 응답이 5초를 넘으면 AI 챗봇 Callback 권한을 신청하고 블록의 Callback API를 켭니다.

## 검증

```powershell
python -m unittest discover -s tests -v
```

테스트는 사용자·봇 신원 전달, 전용 Adapter token, 설정 누락 시 fail-closed, 4초 제한, Callback,
Callback URL 검증과 SimpleText 1,000자 제한을 확인합니다.
