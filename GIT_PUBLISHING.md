# Publish this local Git repository

This archive includes a local `.git` repository with actual import, feature, docs and audit-key commits. The earlier development snapshot arrived as ZIP files without Git history, so these commits do **not** recreate the organizer's requested week-spanning history. Do not backdate or invent commits.

## Publish to a new public GitHub repository

1. Create a new **empty public** repository on GitHub. Do not add a README, license or `.gitignore` there because this repository already contains them.
2. In VS Code terminal, from the `trustvault-starter` folder, set the remote URL to the repository you created (replace the example URL with your real one):

   ```powershell
   git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-REPOSITORY.git
   git branch -M main
   git push -u origin main
   ```

   If GitHub requires authentication, sign in through your Git Credential Manager; never place a personal access token in a command, source file, or `.env`.
3. Open `PROMPTS.md` and replace the local short commit references with the real public URLs copied from GitHub. Do not alter prior commit timestamps to make the history look older.
4. Continue making real, small commits as you perform final browser tests, fixes, deployment and demo recording. Your current local commits are all from this challenge-alignment session; they are not a substitute for the original week-long development history.
5. Check `git status --short` and `git log --oneline --decorate -8` before sharing the repository. Make sure no `.env`, real credential, test database, private upload or API key is tracked.

## Items this guide cannot complete by itself

Publishing requires a GitHub account/repository and user authorization. A public repository URL, hosted HTTPS application, judge credentials and a five-minute video are not included in this local ZIP. After deployment, place the real live URL and role credentials in the README (use unique credentials generated for the deployment, never the development sample passwords) and link the real video. The provided `DEMO_SCRIPT.md` is an outline, not a recorded video.
