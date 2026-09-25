# Qoo10 小規模事前検証ツール

Qoo10の公開検索URLをブラウザで開き、最大10商品を対象にCSVと画像を生成する検証版です。ログインやプロキシは使いません。CAPTCHA、ロボット認証、523、アクセス拒否を検知した場合は停止してログへ記録し、回避は行いません。

## 実行

1. `config.example.json` を `config.json` にコピーします。
2. `search_url`、`description`、`max_products` を編集します。
3. 次をPowerShellで実行します。

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python qoo10_scraper.py --config config.json
```

`output` フォルダに次を保存します。

- `qoo10_sample.csv`: 種類名を取得できた商品のみ。種類ごとに1行。
- `images`: 600x600、JPG形式の画像。
- `failures.csv`: 種類、価格、アクセス制限などの未取得理由。
- `run_log.jsonl`: 開始、商品単位の結果、ブロック検知。
- `summary.json`: 行数、失敗数、画像数、処理時間。

## EXE作成

```powershell
.\build_exe.ps1
```

生成先は `dist\Qoo10ValidationScraper.exe` です。Playwrightのブラウザ本体は別ファイルのため、完全な単一EXE配布ではブラウザ同梱用インストーラーの追加作業が必要です。検証版は端末にChromeがある場合、`browser_channel` を `chrome` にして利用できます。

## 制約

- 購入操作、ログイン、CAPTCHA解除、アクセス制限の突破は行いません。
- Qoo10側の表示構造変更で抽出箇所が変わる可能性があります。
- 種類情報がDOMに表示されない商品はCSVへ仮行を作らず、`failures.csv` に記録します。
- C列の本番文章は提供されたサンプルCSVの内容へ置き換えてください。
