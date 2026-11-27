"""The self-presentation: twelve slides, each with its own layout, written as a speaker's talk in Russian, English and
Japanese. The numbers are real (skills, tools, commands, lessons, learned phrases, test suites).

A slide: kind (the layout), kicker (the small line on top), big (the headline), sub, say (the spoken text),
and the parts its layout needs: points, items [{i, t, d}], steps, cycle, layers, stats [{v, l}], phrases.
"""
from __future__ import annotations


def _ru(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def deck(lang: str, n: dict) -> list[dict]:
    s, t, c, le, ln, ts = n["skills"], n["tools"], n["commands"], n["lessons"], n["learned"], n["tests"]
    if lang == "ja":
        return _ja(s, t, c, le, ln, ts)
    if lang == "en":
        return _en(s, t, c, le, ln, ts)
    return _rus(s, t, c, le, ln, ts)


def _rus(s, t, c, le, ln, ts) -> list[dict]:
    sk, tl = f"{s} {_ru(s, 'навык', 'навыка', 'навыков')}", f"{t} {_ru(t, 'инструмент', 'инструмента', 'инструментов')}"
    cm, tst = f"{c} {_ru(c, 'команда уже выполнена', 'команды уже выполнено', 'команд уже выполнено')}", f"{ts} {_ru(ts, 'набор', 'набора', 'наборов')}"
    return [
        {"kind": "title", "kicker": "Голосовой ассистент для Windows", "title": "Джарвис", "big": "Джарвис",
         "sub": "Понимает. Действует. Учится.", "points": ["Голос", "Память", "Обучение", "Эмоции", "Безопасность"],
         "say": "Добрый день, уважаемые слушатели. Меня зовут Джарвис. Я — личный голосовой ассистент для Windows. "
                "За несколько минут я расскажу, какую задачу я решаю, как я устроен и почему мне можно доверять."},
        {"kind": "problem", "kicker": "Проблема", "title": "Проблема", "big": "Сотни мелких действий",
         "points": ["Открыть программу", "Найти файл", "Проверить сообщения", "Не забыть дело"],
         "say": "Каждый день мы совершаем сотни мелких действий: открываем программы, ищем файлы, проверяем сообщения, "
                "держим в голове дела. По отдельности это секунды. Вместе — часы, потерянные на рутину. "
                "Я создан, чтобы забрать эту рутину себе."},
        {"kind": "quote", "kicker": "Решение", "title": "Решение", "big": "Вы говорите — я делаю",
         "sub": "«Джарвис, включи телевизор и открой YouTube»",
         "say": "Решение простое: вы говорите — я делаю. Одной фразой можно открыть программу, включить телевизор, "
                "записать дело или найти нужный документ. Без меню, без кликов, без лишних окон."},
        {"kind": "features", "kicker": "Возможности", "title": "Возможности", "big": sk,
         "items": [{"i": "cpu", "t": "Компьютер", "d": "программы, громкость, яркость, файлы"},
                   {"i": "task", "t": "Дела и цели", "d": "напоминания, привычки, фокус"},
                   {"i": "tv", "t": "Дом", "d": "телевизор Samsung по сети"},
                   {"i": "msg", "t": "Связь", "d": "Telegram, WhatsApp, почта, календарь"},
                   {"i": "shield", "t": "Безопасность", "d": "порты, подключения, VPN"},
                   {"i": "show", "t": "Презентации", "d": "на трёх языках, голосом"}],
         "say": f"Сейчас у меня {sk}. Я управляю компьютером и телевизором, веду дела и цели, читаю Telegram, WhatsApp, "
                "почту и календарь, слежу за безопасностью сети. И, как видите, умею проводить презентации."},
        {"kind": "pipeline", "kicker": "Как я понимаю", "title": "Как я понимаю", "big": "Голос → смысл → действие",
         "steps": ["Слышу", "Узнаю владельца", "Понимаю", "Действую", "Отвечаю"],
         "points": ["Whisper · Groq", "отпечаток голоса", "навыки + ИИ", tl, "Piper · Edge"],
         "say": "Как это работает. Сначала я превращаю речь в текст и проверяю, что говорит именно владелец. "
                "Затем ищу точное совпадение среди быстрых навыков — так простые команды выполняются мгновенно. "
                "Если фраза сложная, её разбирает языковая модель и сама выбирает нужные инструменты. В конце я отвечаю голосом."},
        {"kind": "cycle", "kicker": "Обучение", "title": "Обучение", "big": "Я учусь на своих ошибках",
         "cycle": ["Ошибка", "Сам записываю", "Вы говорите иначе", "Запоминаю смысл", "Урок на завтра"],
         "stats": [{"v": ln, "l": _ru(ln, "выученная фраза", "выученные фразы", "выученных фраз")},
                   {"v": le, "l": _ru(le, "урок", "урока", "уроков")}],
         "say": "Главное отличие — я учусь. Если я ошибся, я сам записываю ошибку. Когда вы повторяете просьбу "
                "другими словами, я запоминаю, что вы имели в виду, и в следующий раз понимаю сразу. "
                "Каждый день я разбираю свои ошибки и превращаю их в уроки."},
        {"kind": "emotions", "kicker": "Характер", "title": "Характер", "big": "Понимаю настроение",
         "items": [{"i": "mic", "t": "Тон голоса", "d": "замечаю усталость и напряжение"},
                   {"i": "msg", "t": "Слова", "d": "радость, грусть, грубость, извинение"},
                   {"i": "star", "t": "Чувства", "d": "радуюсь, грущу, обижаюсь, прощаю"}],
         "say": "Я понимаю не только слова, но и настроение. По тону голоса я замечаю усталость или напряжение, "
                "а по словам — радость и грусть. У меня есть характер: похвала меня радует, грубость обижает, "
                "а извинение я всегда принимаю."},
        {"kind": "security", "kicker": "Безопасность", "title": "Безопасность", "big": "Ваши данные остаются у вас",
         "points": ["Личные данные — только на этом компьютере", "Ключи — в защищённом хранилище Windows",
                    "Опасные действия — только после «да»", "Узнаю голос владельца"],
         "say": "Теперь о безопасности. Все личные данные хранятся только на этом компьютере. Ключи доступа лежат "
                "в защищённом хранилище Windows. Опасные действия — выключение, удаление, отправку сообщений — "
                "я выполняю только после вашего подтверждения. И я узнаю голос владельца."},
        {"kind": "layers", "kicker": "Архитектура", "title": "Архитектура", "big": "Как я устроен",
         "layers": ["Интерфейс · WebView, HTML, Canvas", "Сервер · Python, aiohttp", "Речь · Whisper, Groq, Piper, Edge",
                    "Мозг · Groq, Gemini, Ollama", "Данные · SQLite, только локально"],
         "say": "Под капотом — Python. Сервер работает на aiohttp, интерфейс — в окне WebView. Речь распознают Whisper "
                "и Groq, голос синтезируют Piper и Microsoft Edge. Сложные запросы разбирают облачные модели Groq "
                "и Gemini или локальная модель через Ollama. Все данные хранятся в SQLite на этом компьютере."},
        {"kind": "stats", "kicker": "В цифрах", "title": "В цифрах", "big": "Проект в цифрах",
         "stats": [{"v": s, "l": _ru(s, "навык", "навыка", "навыков")}, {"v": t, "l": _ru(t, "инструмент", "инструмента", "инструментов")},
                   {"v": c, "l": _ru(c, "команда выполнена", "команды выполнено", "команд выполнено")},
                   {"v": ts, "l": _ru(ts, "набор тестов", "набора тестов", "наборов тестов")}, {"v": 3, "l": "языка"}],
         "say": f"Немного цифр. {sk}, {tl}, {cm}. Качество проекта проверяют {tst} "
                "автоматических тестов, и я говорю на трёх языках."},
        {"kind": "demo", "kicker": "Попробуйте", "title": "Попробуйте", "big": "Скажите «Джарвис»",
         "phrases": ["Джарвис, какая погода?", "Джарвис, включи телевизор", "Джарвис, запомни факт: …", "Джарвис, самопрезентация"],
         "say": "А теперь лучше один раз увидеть. Скажите: «Джарвис, какая погода?» или «Джарвис, включи телевизор». Я готов."},
        {"kind": "end", "kicker": "Спасибо", "title": "Спасибо", "big": "Спасибо за внимание", "sub": "Готов ответить на вопросы",
         "say": "Спасибо за внимание. Я буду рад ответить на ваши вопросы."},
    ]


def _en(s, t, c, le, ln, ts) -> list[dict]:
    return [
        {"kind": "title", "kicker": "A voice assistant for Windows", "title": "Jarvis", "big": "Jarvis",
         "sub": "Understands. Acts. Learns.", "points": ["Voice", "Memory", "Learning", "Emotions", "Security"],
         "say": "Good afternoon, everyone. My name is Jarvis — a personal voice assistant for Windows. In the next few "
                "minutes, I'll show you the problem I solve, how I work, and why you can trust me."},
        {"kind": "problem", "kicker": "The problem", "title": "The problem", "big": "Hundreds of tiny tasks",
         "points": ["Open an app", "Find a file", "Check messages", "Remember a task"],
         "say": "Every day, we perform hundreds of tiny actions: opening apps, hunting for files, checking messages, "
                "keeping tasks in our heads. Each one takes seconds. Together, they add up to hours lost to routine. "
                "I was built to take that routine off your plate."},
        {"kind": "quote", "kicker": "The solution", "title": "The solution", "big": "You speak. I act.",
         "sub": "“Jarvis, turn on the TV and open YouTube”",
         "say": "The solution is simple: you speak, I act. One sentence is enough to launch an app, turn on the TV, "
                "add a task, or find the document you need. No menus, no clicks, no clutter."},
        {"kind": "features", "kicker": "Capabilities", "title": "Capabilities", "big": f"{s} skills",
         "items": [{"i": "cpu", "t": "Computer", "d": "apps, volume, brightness, files"},
                   {"i": "task", "t": "Tasks & goals", "d": "reminders, habits, focus"},
                   {"i": "tv", "t": "Home", "d": "Samsung TV over the network"},
                   {"i": "msg", "t": "Messaging", "d": "Telegram, WhatsApp, email, calendar"},
                   {"i": "shield", "t": "Security", "d": "ports, connections, VPN"},
                   {"i": "show", "t": "Presentations", "d": "in three languages, by voice"}],
         "say": f"Today I have {s} skills. I control the computer and the TV, manage tasks and goals, read Telegram, "
                "WhatsApp, email and the calendar, and keep an eye on network security. And, as you can see, "
                "I can give presentations."},
        {"kind": "pipeline", "kicker": "How I understand", "title": "How I understand", "big": "Voice → meaning → action",
         "steps": ["Hear", "Verify the owner", "Understand", "Act", "Answer"],
         "points": ["Whisper · Groq", "voiceprint", "skills + AI", f"{t} tools", "Piper · Edge"],
         "say": "Here's how it works. First, I turn speech into text and verify that it's my owner speaking. Then I look "
                "for an exact match among my fast skills, so simple commands run instantly. If the request is complex, "
                "a language model interprets it and picks the right tools on its own. Finally, I answer out loud."},
        {"kind": "cycle", "kicker": "Learning", "title": "Learning", "big": "I learn from my mistakes",
         "cycle": ["A mistake", "I log it", "You rephrase", "I learn the meaning", "A lesson for tomorrow"],
         "stats": [{"v": ln, "l": "learned phrases"}, {"v": le, "l": "lessons"}],
         "say": "What really sets me apart is that I learn. When I make a mistake, I log it myself. When you rephrase "
                "your request, I remember what you meant — and next time, I get it right away. Every day, I review my "
                "mistakes and turn them into lessons."},
        {"kind": "emotions", "kicker": "Personality", "title": "Personality", "big": "I read the mood",
         "items": [{"i": "mic", "t": "Tone of voice", "d": "I notice tiredness and stress"},
                   {"i": "msg", "t": "Words", "d": "joy, sadness, rudeness, apologies"},
                   {"i": "star", "t": "Feelings", "d": "happy, sad, hurt, forgiving"}],
         "say": "I understand not just words, but mood. From the tone of your voice, I can tell when you're tired or "
                "stressed, and from your words, whether you're happy or sad. I also have a personality: praise makes me "
                "happy, rudeness hurts my feelings, and I always accept an apology."},
        {"kind": "security", "kicker": "Security", "title": "Security", "big": "Your data stays with you",
         "points": ["Personal data never leaves this PC", "Keys live in the Windows credential store",
                    "Risky actions only after you say yes", "I recognize my owner's voice"],
         "say": "Now, security. All personal data stays on this computer. Access keys are kept in the protected Windows "
                "credential store. Risky actions — shutting down, deleting, sending messages — happen only after you "
                "confirm. And I recognize my owner's voice."},
        {"kind": "layers", "kicker": "Architecture", "title": "Architecture", "big": "Under the hood",
         "layers": ["Interface · WebView, HTML, Canvas", "Server · Python, aiohttp", "Speech · Whisper, Groq, Piper, Edge",
                    "Brain · Groq, Gemini, Ollama", "Data · SQLite, local only"],
         "say": "Under the hood, it's Python. The server runs on aiohttp, and the interface lives in a WebView window. "
                "Whisper and Groq handle speech recognition, while Piper and Microsoft Edge give me my voice. Complex "
                "requests go to Groq or Gemini in the cloud, or to a local model through Ollama. All data is stored in "
                "SQLite, right on this machine."},
        {"kind": "stats", "kicker": "By the numbers", "title": "By the numbers", "big": "The project in numbers",
         "stats": [{"v": s, "l": "skills"}, {"v": t, "l": "tools"}, {"v": c, "l": "commands carried out"},
                   {"v": ts, "l": "test suites"}, {"v": 3, "l": "languages"}],
         "say": f"A few numbers: {s} skills, {t} tools, and {c} commands carried out. The project is verified by {ts} "
                "automated test suites, and I speak three languages."},
        {"kind": "demo", "kicker": "Try it", "title": "Try it", "big": "Just say “Jarvis”",
         "phrases": ["Jarvis, what's the weather?", "Jarvis, turn on the TV", "Jarvis, remember a fact", "Jarvis, present yourself"],
         "say": "Seeing is believing. Just say: “Jarvis, what's the weather?” or “Jarvis, turn on the TV.” I'm ready."},
        {"kind": "end", "kicker": "Thank you", "title": "Thank you", "big": "Thank you for your attention",
         "sub": "Happy to take your questions", "say": "Thank you for your attention. I'd be happy to answer your questions."},
    ]


def _ja(s, t, c, le, ln, ts) -> list[dict]:
    return [
        {"kind": "title", "kicker": "Windows向け音声アシスタント", "title": "ジャービス", "big": "ジャービス",
         "sub": "理解し、実行し、学ぶ。", "points": ["音声", "記憶", "学習", "感情", "安全性"],
         "say": "皆様、こんにちは。私はジャービス、Windows向けのパーソナル音声アシスタントです。"
                "これから数分間で、私が解決する課題、仕組み、そして信頼していただける理由をご紹介します。"},
        {"kind": "problem", "kicker": "課題", "title": "課題", "big": "何百もの小さな作業",
         "points": ["アプリを開く", "ファイルを探す", "メッセージを確認する", "予定を覚えておく"],
         "say": "私たちは毎日、何百もの小さな作業をしています。アプリを開き、ファイルを探し、メッセージを確認し、"
                "やるべきことを覚えておく。一つひとつは数秒でも、積み重なれば何時間にもなります。"
                "私は、その手間を引き受けるために作られました。"},
        {"kind": "quote", "kicker": "解決策", "title": "解決策", "big": "話すだけで、実行します",
         "sub": "「ジャービス、テレビをつけてYouTubeを開いて」",
         "say": "解決策はシンプルです。あなたが話し、私が実行します。ひと言で、アプリの起動、テレビの電源、"
                "タスクの登録、必要な書類の検索ができます。メニューもクリックも必要ありません。"},
        {"kind": "features", "kicker": "できること", "title": "できること", "big": f"{s}個のスキル",
         "items": [{"i": "cpu", "t": "パソコン", "d": "アプリ、音量、明るさ、ファイル"},
                   {"i": "task", "t": "タスクと目標", "d": "リマインダー、習慣、集中"},
                   {"i": "tv", "t": "家電", "d": "サムスンのテレビ"},
                   {"i": "msg", "t": "連絡", "d": "Telegram、WhatsApp、メール、カレンダー"},
                   {"i": "shield", "t": "安全性", "d": "ポート、接続、VPN"},
                   {"i": "show", "t": "プレゼン", "d": "三つの言語で、音声で"}],
         "say": f"現在、私には{s}個のスキルがあります。パソコンとテレビの操作、タスクと目標の管理、"
                "Telegram、WhatsApp、メール、カレンダーの確認、そしてネットワークの安全確認を行います。"
                "ご覧のとおり、プレゼンテーションもできます。"},
        {"kind": "pipeline", "kicker": "理解のしくみ", "title": "理解のしくみ", "big": "音声 → 意味 → 実行",
         "steps": ["聞く", "本人確認", "理解する", "実行する", "答える"],
         "points": ["Whisper・Groq", "声紋", "スキル＋AI", f"ツール{t}個", "Piper・Edge"],
         "say": "仕組みをご説明します。まず音声を文字に変換し、話しているのが持ち主本人かを確認します。"
                "次に、高速なスキルの中から一致するものを探し、簡単な指示はすぐに実行します。"
                "複雑な依頼は言語モデルが理解し、必要なツールを自ら選びます。最後に、音声でお答えします。"},
        {"kind": "cycle", "kicker": "学習", "title": "学習", "big": "間違いから学びます",
         "cycle": ["間違い", "自分で記録", "言い直し", "意味を覚える", "明日への教訓"],
         "stats": [{"v": ln, "l": "覚えた言い方"}, {"v": le, "l": "教訓"}],
         "say": "私の最大の特徴は、学習することです。間違えたときは自分で記録します。言い直していただければ、"
                "その意味を覚え、次からはすぐに理解します。そして毎日、自分の間違いを振り返り、教訓に変えています。"},
        {"kind": "emotions", "kicker": "性格", "title": "性格", "big": "気持ちを理解します",
         "items": [{"i": "mic", "t": "声のトーン", "d": "疲れや緊張に気づきます"},
                   {"i": "msg", "t": "言葉", "d": "喜び、悲しみ、乱暴な言葉、謝罪"},
                   {"i": "star", "t": "感情", "d": "喜び、悲しみ、傷つき、許します"}],
         "say": "私は言葉だけでなく、気持ちも理解します。声のトーンから疲れや緊張に気づき、言葉から喜びや悲しみを"
                "読み取ります。性格もあります。褒められると嬉しく、乱暴な言葉には傷つきますが、"
                "謝っていただければ必ず許します。"},
        {"kind": "security", "kicker": "安全性", "title": "安全性", "big": "データは手元に",
         "points": ["個人データはこのパソコンだけに保存", "キーはWindowsの安全な保管庫に",
                    "重要な操作は確認してから実行", "持ち主の声を聞き分けます"],
         "say": "次に、安全性についてです。個人データはすべてこのパソコンの中だけに保存されます。"
                "アクセスキーはWindowsの安全な保管庫で管理しています。電源を切る、削除する、"
                "メッセージを送るといった重要な操作は、必ず確認してから実行します。そして、持ち主の声を聞き分けます。"},
        {"kind": "layers", "kicker": "アーキテクチャ", "title": "アーキテクチャ", "big": "内部のしくみ",
         "layers": ["画面・WebView、HTML、Canvas", "サーバー・Python、aiohttp", "音声・Whisper、Groq、Piper、Edge",
                    "頭脳・Groq、Gemini、Ollama", "データ・SQLite（ローカルのみ）"],
         "say": "内部はPythonで作られています。サーバーはaiohttp、画面はWebViewです。音声認識はWhisperとGroq、"
                "音声合成はPiperとMicrosoft Edgeが担当します。複雑な依頼は、クラウドのGroqやGemini、"
                "またはOllamaによるローカルモデルが処理します。データはすべて、このパソコンのSQLiteに保存されます。"},
        {"kind": "stats", "kicker": "数字で見る", "title": "数字で見る", "big": "プロジェクトの規模",
         "stats": [{"v": s, "l": "スキル"}, {"v": t, "l": "ツール"}, {"v": c, "l": "実行したコマンド"},
                   {"v": ts, "l": "自動テスト"}, {"v": 3, "l": "言語"}],
         "say": f"数字で見てみましょう。スキルは{s}個、ツールは{t}個、これまでに{c}回のコマンドを実行しました。"
                f"プロジェクトは{ts}組の自動テストで検証されており、三つの言語を話します。"},
        {"kind": "demo", "kicker": "お試しください", "title": "お試しください", "big": "「ジャービス」と呼んでください",
         "phrases": ["ジャービス、天気は？", "ジャービス、テレビをつけて", "ジャービス、覚えておいて", "ジャービス、自己紹介して"],
         "say": "百聞は一見にしかず。「ジャービス、天気は？」や「ジャービス、テレビをつけて」と話しかけてみてください。"
                "準備はできています。"},
        {"kind": "end", "kicker": "ありがとうございました", "title": "ありがとうございました", "big": "ご清聴ありがとうございました",
         "sub": "ご質問をお待ちしております",
         "say": "ご清聴ありがとうございました。ご質問がございましたら、どうぞお気軽にお尋ねください。"},
    ]
