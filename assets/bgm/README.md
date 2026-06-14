# BGM Assets

이 디렉토리에는 YouTube Audio Library에서 받은 BGM 파일을 둔다.

권장 절차:

1. YouTube Studio -> Audio Library로 이동한다.
2. 필터에서 `Attribution not required`를 선택한다.
3. 사용할 곡 3~5개를 내려받아 이 디렉토리에 저장한다.
4. 저작자 표시가 필요한 곡을 대비해 `credits.json`에 파일명별 문구를 기록한다.

예시:

```json
{
  "example-cc-by-track.mp3": "Music: Track Title by Artist, YouTube Audio Library"
}
```

저작자 표시가 필요 없는 곡은 `credits.json`에 넣지 않거나 빈 문자열로 둔다.
