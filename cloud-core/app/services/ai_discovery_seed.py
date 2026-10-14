"""Initial AI Resource Discovery corpus (REQ-AIC-011): the owner-supplied list
(2026-09-25). Types are PROPOSED from general knowledge and labelled as such;
every entry starts DISCOVERED. Nothing here claims an API, price, quota or
active integration — each needs verification against an official source."""
BASIS = "INFERENCE: proposed from general knowledge; not verified against an official source"
SOURCE = "owner-supplied list, 2026-09-25"
_L = "APPLICATION"; _P = "PROVIDER"; _M = "MODEL"; _R = "RESEARCH_TOOL"; _A = "ACADEMIC_TOOL"; _D = "DOCUMENT_TOOL"
_S = "SEARCH_TOOL"; _W = "WRITING_TOOL"; _E = "EDUCATION_TOOL"; _V = "VISION_TOOL"; _AU = "AUDIO_TOOL"; _X = "PARSING_TOOL"
ENTRIES = [
    ("ChatGPT", [_L]), ("OpenAI API", [_P]), ("Bing / Copilot", [_L, _S]), ("My AI (Snapchat)", [_L]),
    ("Google Bard / Gemini", [_L]), ("Google Gemini API", [_P]), ("BlenderBot", [_M]), ("Einstein GPT", [_L]),
    ("Jasper", [_L, _W]), ("You.com", [_L, _S]), ("Nova", [_L]), ("Scalenut", [_L, _W]), ("INK", [_L, _W]),
    ("NeuralText", [_L, _W]), ("Writesonic", [_L, _W]), ("Wordtune", [_L, _W]), ("Sapling", [_L, _W]), ("Rytr", [_L, _W]),
    ("Chibi AI", [_L, _W]), ("Sudowrite", [_L, _W]), ("Scholarcy", [_R, _A]), ("Humata", [_R, _D]),
    ("AskYourPDF", [_D]), ("KodeKloud AI", [_E]), ("Picma", [_V]), ("YouLearn", [_E]), ("ClassAce", [_E]),
    ("Hugging Face Hub", [_M]), ("Hugging Face Inference API", [_P]), ("Llama", [_M]), ("Claude.ai", [_L]),
    ("Anthropic API", [_P]), ("GPTZero", [_L]), ("Turnitin AI", [_L, _A]), ("AvalAI", [_P]), ("Connected Papers", [_R, _A]),
    ("Epsilon AI", [_R]), ("Mapify", [_L]), ("Qwen", [_M]), ("Ideogram", [_V]), ("Listnr", [_AU]), ("Taskade", [_L]),
    ("TalkAI", [_L]), ("Iris.ai", [_R, _A]), ("PoolParty", [_L]), ("Semantic AI", [_L]), ("Regie", [_L, _W]),
    ("Consensus", [_R, _A]), ("Napkin", [_V]), ("GapGPT", [_L]), ("Poe", [_L]), ("Arena", [_L]), ("Felo", [_S]),
    ("Blackbox", [_L]), ("Paperpal / Editage", [_W, _A]), ("X-doc", [_D]), ("Atlas", [_L]), ("Muse", [_L]),
    ("Atria", [_L]), ("Cathoven", [_E]), ("ResearchRabbit", [_R, _A]), ("EdrawMax", [_V]), ("Sakana", [_M]),
    ("Kimi", [_L, _M]), ("Robo", [_L]), ("Zigap", [_L]), ("Hoshify", [_L]), ("NoteGPT", [_L]), ("Julius AI", [_L]),
    ("Jenni", [_W, _A]), ("Scite", [_R, _A]), ("OpenRead", [_R, _A]), ("Wisio", [_W, _A]), ("Elicit", [_R, _A]),
    ("Perplexity", [_L, _S]), ("Perplexity API", [_P]), ("Scholar GPT", [_L, _A]), ("Semantic Scholar", [_R, _A, _S]),
    ("Scopus AI", [_R, _A]), ("Supersymmetry", [_L]), ("Lateral", [_R]), ("Explainpaper", [_R, _A]),
    ("ResearchMate Pro", [_R]), ("Sharly", [_D]), ("StudyFlo", [_E]), ("Unriddle", [_R, _D]), ("Inciteful", [_R, _A]),
    ("Litmaps", [_R, _A]), ("Paper2Agent", [_R]), ("SciencePro", [_R]), ("MinerU", [_X, _D]), ("Cohere Parse", [_X, _D]),
    # model families from registries (MODEL only; availability through any provider unverified)
    ("GPT", [_M]), ("DeepSeek", [_M]), ("Mistral", [_M]), ("Mixtral", [_M]), ("Gemma", [_M]), ("GLM", [_M]),
    ("Cohere Command", [_M]), ("Phi", [_M]), ("Granite", [_M]), ("Falcon", [_M]), ("BERT family", [_M]), ("T5 family", [_M]),
    ("BLOOM", [_M]), ("DBRX", [_M]), ("Nemotron", [_M]), ("OLMo", [_M]), ("Jamba", [_M]), ("MiniMax", [_M]),
    ("EXAONE", [_M]), ("Yi", [_M]), ("RWKV", [_M]), ("Mamba", [_M]),
]
