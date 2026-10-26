# Actual browser preview qualification

2026-10-26 23:43 UTC. Application source d20bac5dc7d8e3b10fa5e8fb7e033d9bc6d79d37; final 393px QA fixture ecce63cb22f6a6f1ba41cfdfea8bb30b20e270ff. App bytes are unchanged from the 475-test qualification.

Actual cloud Chromium loaded the selected dist-owner files from loopback HTTP. Desktop DOM width and scrollWidth were both1165px. The explicitly labeled narrow iframe had clientWidth and scrollWidth both393px, height1000px; its footer occupied y739.89–839.64px. Screenshots showed readable wrapping, spaced controls, no overlap or horizontal clipping, and clear HTTP-unavailable messaging. This is a real browser CSS/DOM check, not mobile-device emulation.

Both views showed HTTPS-required/unavailable, disabled secret input and sign-in, and a hidden workspace. No credentials were entered, no successful auth response was simulated in this browser, and no TLS bypass was used. The cloud Terminal static-server log showed owner HTML/JS/CSS200, later cached304, and no /owner/auth requests. An incidental /favicon.ico404 occurred. Exact served HTML/JS/CSS SHA256 values matched BUILD_SHA256.json, verified again in the cloud Terminal.

This does not establish actual owner login/session/logout, HTTPS/proxy security, private workspace integration, inference or worker-plus-supervisor benchmark, payment, deployment, or latest-source recovery. Successful auth behavior is still authored controller/DOM and synthetic ASGI evidence only. Screenshots, browser state and raw terminal logs are not committed. A full-page capture timed out; the normal viewport screenshot and DOM metrics were available and inspected.
