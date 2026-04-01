PLATFORM: linkedin
TYPE: single
---
Claude Code's source code didn't get hacked. Bun just served it by default.

The bug had been sitting open for 20 days. Bun includes source maps in production builds unless you explicitly disable them. Someone checked the Claude Code npm package and pulled 512,000 lines of Anthropic's source. It became one of the highest-voted HN threads of 2026. Not because someone was clever. Because the build tool shipped what it was configured to ship.

I checked my own build output within an hour. I build with Bun. I publish packages. For a minute I just stared at the terminal, making sure I hadn't been shipping source I didn't mean to. The same default I'd been running.

Same 48 hours: Axios got compromised via stolen maintainer credentials, 83M weekly downloads, cross-platform RAT dropped in the update. LiteLLM had a poisoned PyPI publish that CI/CD pipelines auto-consumed and exfiltrated SSH keys and cloud credentials from an estimated 36% of cloud environments. Three different attack surfaces, one weekend. None required a sophisticated exploit. Just defaults nobody audited, credentials nobody rotated, and package managers that trust whatever gets published.

The part I can't shake: how many packages built with Bun are currently shipping source maps without the authors knowing? Claude Code got noticed because it's Anthropic. Most won't.

When did you last check what your build toolchain actually ships?

https://mindpattern.ai
---
