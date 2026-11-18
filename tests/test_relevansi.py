import relevansi


def test_repo_skill_jelas_relevan():
    nilai = relevansi.skor("NVIDIA/skills", "Agent Skills for NVIDIA products - install into Claude Code")
    assert relevansi.relevan(nilai)


def test_repo_tak_terkait_tidak_relevan():
    nilai = relevansi.skor("budi/pencatat-uang", "Aplikasi keuangan pribadi", "finance,python")
    assert nilai == 0
    assert not relevansi.relevan(nilai)


def test_hanya_menyebut_agentic_skill_sambil_lalu_tidak_relevan():
    nilai = relevansi.skor("teng-lin/notebooklm-py",
                           "Unofficial Python API and agentic skill for Google Gemini Notebook")
    assert nilai == 3
    assert not relevansi.relevan(nilai)


def test_normalisasi_tanda_baca():
    assert relevansi.normalisasi("Claude-Code, SKILL.md") == " claude code skill md "


def test_topik_ikut_dihitung():
    assert relevansi.skor("a/b", "", "claude-code,skills") >= 4


def test_ambang_bisa_diubah():
    assert relevansi.relevan(3, ambang=3)
    assert not relevansi.relevan(3, ambang=4)


def test_kata_pendukung_tanpa_kata_inti_tidak_cukup():
    # banyak kata pendukung (mcp, cursor, claude code, agentic) tetapi tidak menyebut skill
    nilai = relevansi.skor("x/unity-mcp", "MCP server for Claude Code, Cursor, Copilot, agentic workflows")
    assert nilai < relevansi.config.AMBANG_RELEVAN
    assert not relevansi.relevan(nilai)
