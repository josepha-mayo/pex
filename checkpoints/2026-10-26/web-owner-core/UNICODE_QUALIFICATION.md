# Unicode title compatibility qualification

2026-10-27 03:01 UTC. Source checkpoint69fbefbd30d901645f4c7925d74d58e604a5bab3, reconstructed owner-workspace lane only.

A valid backend title of161 astral emoji was rejected by frontend UTF-16 length, clearing the entire workspace. A temporary authored built-DOM test reproduced the failure (9 existing passed,1 new failed). The frontend now counts Unicode code points, matching Python's320-character bound. Boundary tests cover160/161/320 emoji,320 mixedUnicode, and rejection of321 code points. Built-DOM tests confirm title and neighboring session remain visible.

Fresh npm test:484 passing, zero failures/skips (453 existing +31 owner). Owner TypeScript and Vite build pass;31 owner tests include15 auth,6 workspace,10 built-DOM. No backend source changed or new backend run claimed. Three changed source blobs match remote Git blob identities; source/build manifests refreshed.

All responses are authored local fixtures. No new actual browser verification, live owner authentication, provider access, inference or paired benchmark. Earlier Chromium screenshots/receipts apply only to274dcb1 and its old artifact hashes, not the rebuilt JS/HTML here. CSS is unchanged. Production/live admission gates unchanged. No release/deployment or extra CI jobs launched; review-branch checkpoint uses[skip ci].
