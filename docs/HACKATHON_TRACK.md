# Hackathon & AWS track

Living checklist. Do **not** put secrets, tokens, or account IDs here.

Last updated: 2026-08-27  
Browser used this turn: **yes**. Devpost is logged in (`You're registered`). My projects shows no draft yet. Start project is recaptcha-gated. builder.aws.com was signed out in the IDE browser. `aws sts` is still NoCredentials. Architecture PNG is at `docs/architecture/pex-architecture.png`. Do not Submit until YouTube/Vimeo + Builder ID exist.

## Open pages (user said these are already logged in)

| What | URL | Use when |
| --- | --- | --- |
| Hackathon resources | https://agentsforhumans.devpost.com/resources | Strands/AgentCore docs, $50 credit form |
| Hackathon home | https://agentsforhumans.devpost.com/ | Rules, submit, participant count |
| Rules | https://agentsforhumans.devpost.com/rules | Bonus-post wording before publishing |
| FAQ | https://agentsforhumans.devpost.com/details/faqs | Submission artifacts |
| AWS Builder Center | https://builder.aws.com/ | Bonus posts (up to +0.6 if Stage Two still applies) |
| AWS Builder ID profile | https://profile.aws.amazon.com/#/profile/details | Copy Builder ID into Devpost |
| AWS Console | https://eu-north-1.console.aws.amazon.com/console/home?region=eu-north-1# | Bedrock, AgentCore, CloudWatch |

## Hard dates

| Item | When |
| --- | --- |
| Submission deadline | 14 Sep 2026, 17:00 PDT |
| AWS $50 promo credits request | 11 Sep 2026, 12:00 PT — https://forms.gle/6sjzKiX6bKUMA5NEA |
| Credits expire | 31 Oct 2026 |
| Judging | 15 Sep – 8 Oct 2026 |
| Winners | around 14 Oct 2026 |

## Bonus posts (do these; they score)

Rules (updated 12 Aug 2026): public **builder.aws.com** posts about the AWS build journey. Put **Agents for Humans** in the title. Hashtag `#AgentsforHumans` is no longer required. Re-read rules immediately before publish.

Planned posts (drafts in `docs/posts/`, **not published**):

1. Agents for Humans: Building a Cross-Harness Supervisor with Strands and AgentCore
2. Agents for Humans: Measuring Human Attention as an Agent Benchmark
3. Agents for Humans: Designing Safe Autonomous Approvals Across Coding Agents

Status: **0 / 3 published**. Do not publish empty journey posts. Wait until we have a real Strands loop, a real adapter lesson, and a real policy lesson.

## AWS / AgentCore (this machine)

Verified 2026-08-25 against [AgentCore supported regions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html). Product catalog also lists **Amazon Bedrock AgentCore** as available in eu-north-1.

| Check | Status |
| --- | --- |
| Preferred region | **eu-north-1** (Europe/Stockholm) — Runtime microVMs **yes**, Runtime Instances **no** |
| Fallback if a feature is missing | eu-west-1 (Ireland) or eu-central-1 (Frankfurt) |
| AWS CLI | Installed (`aws-cli/2.36.29`). `aws sts get-caller-identity` needs `aws login` — no credentials yet |
| Docker | CLI installed (29.7.2). Engine was down until Docker Desktop was started for deploy |
| Bedrock model access | Unknown until credentials exist |
| AgentCore runtime | Supervisor `/invocations` + `/ping` exist; **not deployed** |
| Strands SDK | Installed in the PEX venv (`strands-agents`) |

When ready to use the console in-browser:

1. Confirm Builder ID on the profile page (needed on Devpost).
2. Request $50 credits if not already requested.
3. Enable Bedrock model access in eu-north-1 (Runtime microVMs are there; Runtime Instances are not).
4. Deploy PEX supervisor with AgentCore CLI (`@aws/agentcore`) only after the local loop is solid.

## Product track vs AWS track

Do not pause product work to click consoles. Browser the AWS pages when we need a credential, a deployment, a screenshot, or a published post.

Current product milestone: live desktop attach (Cursor hooks + Codex App Server + Grok Bot observe) plus PexBench freeze, AgentCore deploy in eu-north-1, submit.
