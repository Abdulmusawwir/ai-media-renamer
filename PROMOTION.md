# Promotion Pack — AI Media Renamer

Posts are intentionally plain-spoken (not AI-polished). Tweak names/numbers before posting.

---

## Reddit

### r/DataHoarder, r/HomeServer, r/selfhosted — problem-led launch post

**Title:** I built a tool that renames my entire media library with AI, and it never leaves my PC

My downloads folder was a graveyard. `IMG_5821.jpg`. `final_v3_really.mp4`. `voice_note_034.m4a`. Every editor I know has the same problem — you spend a whole afternoon just renaming stuff so you can find it later.

So I made a free desktop app that does it for me. You drop in a folder of videos, photos, docs, and audio. It runs a local AI model (llama.cpp or Ollama, so nothing is uploaded anywhere), looks at each file, and renames it something you'd actually search for. `IMG_5821.jpg` becomes `quran_carving_ornate_detail.jpg`. It also writes real metadata tags into the file itself, so Resolve and Premiere can search it.

- Runs fully offline
- Free, open source, Windows EXE — no install, no account
- You review every change in a table before anything is touched; one-click undo
- Also catches duplicate photos/videos/audio before they clutter your drive

GitHub: https://github.com/Abdulmusawwir/ai-media-renamer

Would love feedback from people who manage big libraries. What breaks first?

---

### r/VideoEditing — pain-point post

**Title:** How do you guys name your exported clips? I wrote a tool that does it automatically

I edit as a side hustle and my project folders are a disaster — every export ends up as `export_FINAL2.mp4` and then I can't find anything for the next client. I got fed up and built a small tool.

It watches the first frame + reads the audio track of a clip, then names it like a human would: `beach_sunset_drone_pan`, `interview_founder_funding_talk`. It tags files with metadata that Premiere and DaVinci Resolve can actually read, so you can search your library by keyword instead of scrolling.

It's free, runs on a local AI model (llama.cpp or Ollama — no uploading your clients' footage to anyone), and works for photos, docs, and audio too.

Would any of you use something like this, or is your naming system already under control? (Honest question — maybe I'm solving a problem only I have.)

Repo: https://github.com/Abdulmusawwir/ai-media-renamer

---

### r/Photography — community post

**Title:** 10,000 DSC_#### photos and no way to find anything. Until now.

I shoot events and every memory card comes back as `DSC_0142.jpg` × 500. Organizing them by hand is a whole weekend, and Lightroom keywords only work if you actually keyword them (I don't, until it's too late).

I built a free desktop app that looks at each photo with local AI and names it by what's in it — `beach_sunset_2026`, `quran_carving_ornate_detail` — and writes Windows-searchable tags straight into the file. It also flags near-duplicates so you don't store the same shot 6 times.

Runs entirely offline, so client and family photos never leave your machine.

Would photographers actually trust AI to name their files, or is that too weird? Curious to hear real opinions. https://github.com/Abdulmusawwir/ai-media-renamer

---

## LinkedIn

### Founder / product post

My downloads folder made me build something.

`IMG_5821.jpg`. `final_v3_ACTUAL.mp4`. `voice_note_034.m4a`.

Every creator, editor, and small studio I know loses hours (or whole afternoons) just *renaming files* so they can find them later. It felt like such a dumb problem to still exist in 2026.

So I built AI Media Renamer — a free desktop app that:

- Looks at each video, photo, document, and audio file with a local AI model
- Renames it with a descriptive, searchable name
- Writes metadata tags directly into the file, so DaVinci Resolve, Premiere, and Windows Explorer can all search it
- Runs 100% offline — your footage and client work never touch a server
- Lets you review everything before committing, with one-click undo

Built it from Tanzania, open-sourced it, and it's free forever.

For anyone drowning in a messy media folder — this is for you. And for people who invest in tools people actually use daily, I'd love to talk.

GitHub: https://github.com/Abdulmusawwir/ai-media-renamer

---

### Short "building in public" post

Week 1 of shipping my app: it renames media files using AI that runs on your own computer.

Problem I'm solving: creators and editors waste entire afternoons renaming exports and footage. `final_v2_final.mp4` should not be a filename anyone has to think about.

What it does:
- Watches every frame, reads the audio, transcribes voice notes
- Names files like a human would: `beach_sunset_drone_pan.mp4`
- Writes searchable metadata into the file itself
- Runs locally — no cloud, no uploads, no subscription

Free, open source, Windows EXE. Your downloads folder will thank you.

https://github.com/Abdulmusawwir/ai-media-renamer

---

### Investor-focused post (open to discussion, not a pitch)

I've spent the last while on a problem that literally every content creator and editor has: **organizing a media library without losing a day to it.**

The tool is AI Media Renamer. It names, categorizes, and tags videos, photos, documents, and audio using an on-device model — so it's fast, private, and costs nothing per user. It's been built to appeal to a very specific, very large group: the millions of creators, photographers, and studios who all stare at `IMG_5821.jpg` every day.

Why I think this is interesting as a business, not just a side project:

1. **Clear pain, existing users.** Everyone who's ever edited video knows this pain personally. No education needed.
2. **Local-first = privacy selling point.** No one wants client footage uploaded to a cloud AI. On-device processing is the differentiator and the moat.
3. **Room to grow.** Media libraries only get bigger. Bulk cloud-import, team features, studio editions are all natural next steps.
4. **Already shipping.** Working app, real users, open source, and a roadmap.

I'm building in public and would genuinely love feedback — from creators AND from anyone who's invested in creator tools. If you want to see it: https://github.com/Abdulmusawwir/ai-media-renamer

---

## Other communities to try (beyond IG/FB/X)

| Community | Where | Why it fits |
|---|---|---|
| r/selfhosted + r/HomeServer | Reddit | Local-first/offline angle is their whole ethos |
| r/DataHoarder | Reddit | Big libraries, duplicate detection angle |
| r/VideoEditing | Reddit | Creators with messy exports |
| r/Photography | Reddit | DSC_#### pain is universal |
| r/startups / r/SideProject | Reddit | Building-in-public audience |
| Hacker News "Show HN" | news.ycombinator.com | Devs who love local/offline tools |
| Indie Hackers | indiehackers.com | Exactly the "solo dev building tools" audience |
| Product Hunt | producthunt.com | Launch day = first spike of users + feedback |
| Fiverr / Upwork freelancer forums | Discord/Facebook groups | Self-employed editors with client libraries |
| Videography / editing Discord servers | Discord | Direct audience, real feedback loops |
| Local tech / startup communities | Meetup, WhatsApp/Telegram groups | Personal network warm leads |
| **Submit to newsletters** | Sidebar.io, JS Weekly-style, Self-Hosted newsletter | Small write-up = thousands of eyes |

---

## Getting investor attention with these posts

Investors rarely read your README — they read **signals**. Use these posts to generate the signals:

1. **Ship in public, consistently.** Post the "building in public" LinkedIn post weekly, plus a Reddit post per fortnight. Consistency > polish. Investors search founders who post.
2. **Attach real numbers to every post.** "1,000 files organized" or "212 downloads this week" or "42 stars on GitHub" — even small numbers prove traction. Add one number to each post before posting.
3. **Reply to EVERY comment.** A thread where the founder answers thoughtfully is more convincing than the post itself. Investors look at how you handle feedback.
4. **Ask for the right thing, explicitly.** Close the investor post with "if you've invested in creator tools, I'd love a 20-min intro call." Vague posts get ignored; direct asks get replies.
5. **Post it where investors actually look:** Product Hunt launch, Hacker News "Show HN," LinkedIn, and Indie Hackers. Those four are crawled/checked by angel investors more than any social feed.
6. **Build a tiny proof-of-demand story.** Example: "Three editing studios DM'd me to ask for bulk-import" → that becomes your "validated demand" line in an investor conversation.
7. **Put the repo front and center.** On LinkedIn, a GitHub link with a clean README (like the new one) is a demo all by itself. Investors will click it.
8. **Don't wait for perfect.** Post the imperfect version today. Iterate from real reactions, not guesses.
