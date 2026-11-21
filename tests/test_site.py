"""The landing page in site/ says only what the repo says (LC-B18).

A landing page is the one place a stranger reads before anything else, and it
is hand-written HTML that nothing else in the build touches. Left alone, it
goes stale the first time a version is bumped or a command is renamed. Each
fact on the page that has a source in the repo is checked against that source:

- the version chip against plugins/lc/.claude-plugin/plugin.json
- every /lc:<name> it mentions against plugins/lc/skills/<name>/, both ways
- the /lc:mine report it reprints against the README's copy, line for line
- the lead-time chart's clocks against examples/sample-board.json
- every asset it loads exists under site/, and nothing loads from another host
"""
import html
import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, "site")
PAGE = os.path.join(SITE, "index.html")


def read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return fh.read()


class SitePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = read("site", "index.html")

    def test_version_matches_plugin(self):
        plugin = json.loads(read("plugins", "lc", ".claude-plugin", "plugin.json"))["version"]
        found = re.search(r'id="version">v([^<]+)<', self.page)
        self.assertIsNotNone(found, 'site/index.html has no element with id="version"')
        self.assertEqual(found.group(1), plugin,
                         "site/index.html shows v%s but plugin.json is %s - update the "
                         'id="version" chip when bumping' % (found.group(1), plugin))

    def test_commands_match_skills(self):
        skills = {d for d in os.listdir(os.path.join(REPO, "plugins", "lc", "skills"))
                  if os.path.isfile(os.path.join(REPO, "plugins", "lc", "skills", d, "SKILL.md"))}
        named = set(re.findall(r"/lc:([a-z]+)", self.page))
        self.assertEqual(sorted(named - skills), [],
                         "the page names commands that have no skill directory")
        self.assertEqual(sorted(skills - named), [],
                         "these commands exist but the page never mentions them")

    def test_mine_report_matches_readme(self):
        readme = read("README.md").splitlines()
        start = next(i for i, l in enumerate(readme) if l.startswith("As of 2026-09-16"))
        end = next(i for i in range(start, len(readme)) if readme[i].startswith("```"))
        want = [l.rstrip() for l in readme[start:end]]

        pre = re.search(r"<pre>(.*?)</pre>", self.page, re.S)
        self.assertIsNotNone(pre, "the page has no <pre> report block")
        got = html.unescape(re.sub(r"<[^>]+>", "", pre.group(1))).splitlines()
        got = [l.rstrip() for l in got]
        while got and not got[-1]:
            got.pop()
        while want and not want[-1]:
            want.pop()
        self.assertEqual(got, want,
                         "the /lc:mine report on the page differs from the README's")

    def test_chart_matches_sample_board(self):
        board = json.loads(read("examples", "sample-board.json"))
        rows = board.get("results", board)
        by_url = {r["url"]: r["Story ID"] for r in rows}
        sample = {r["Story ID"]: r for r in rows}

        clocks = re.findall(
            r"\{id:'([A-Z]+-\d+)', name:'[^']*', min:(\d+), max:(\d+), after:\[([^\]]*)\]\}",
            self.page)
        self.assertTrue(clocks, "found no clocks in the page's chart data")
        for sid, lo, hi, after in clocks:
            row = sample.get(sid)
            self.assertIsNotNone(row, "%s is charted but not on the sample board" % sid)
            self.assertEqual((int(lo), int(hi)), (row["Lead days min"], row["Lead days max"]),
                             "%s's lead days differ from the sample board" % sid)
            charted = sorted(re.findall(r"'([A-Z]+-\d+)'", after))
            blockers = sorted(by_url.get(u, u) for u in row["Blocked by"])
            self.assertEqual(charted, blockers, "%s's blockers differ from the sample board" % sid)

    def test_assets_are_local_and_present(self):
        refs = re.findall(r'(?:src|href)="([^"#]+)"', self.page)
        refs += re.findall(r'url\("?([^")]+)"?\)', self.page)
        for ref in refs:
            if ref.startswith(("https://github.com/", "https://peter3605.github.io/")):
                continue
            self.assertNotRegex(ref, r"^(https?:)?//", "the page loads %s from another host" % ref)
            self.assertTrue(os.path.isfile(os.path.join(SITE, ref)), "%s is missing from site/" % ref)
        for host in ("fonts.googleapis.com", "fonts.gstatic.com"):
            self.assertNotIn(host, self.page)

    def test_every_font_has_its_licence(self):
        fonts = os.listdir(os.path.join(SITE, "fonts"))
        families = {"archivo": "OFL-Archivo.txt", "ibmplexsans": "OFL-IBMPlexSans.txt",
                    "ibmplexmono": "OFL-IBMPlexMono.txt"}
        for f in fonts:
            if f.endswith(".woff2"):
                family = re.match(r"[a-z]+", f).group(0)
                self.assertIn(family, families, "%s has no known licence file" % f)
                self.assertIn(families[family], fonts, "%s ships without its OFL" % f)


if __name__ == "__main__":
    unittest.main()
