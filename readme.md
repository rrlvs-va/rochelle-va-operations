Rochelle VA + Operations Website — Portfolio-Ready Build
This version adds a Portfolio section to the existing one-page site.
Recommended setup
Use one external portfolio-library URL so the website itself does not need to be rebuilt every time a sample changes.
Easiest option: Google Drive folder
Create a folder such as Rochelle V. Silvestre — Portfolio.
Set the folder to Anyone with the link — Viewer.
Upload only portfolio samples you have reviewed and approved.
Copy the folder link.
Open index.html in a text editor.
Find: const PORTFOLIO_LIBRARY_URL = "";
Paste the public folder URL between the quotation marks.
Commit the updated index.html to the GitHub repo connected to Wasmer.
After this one-time setup, you can add, replace, rename, or delete portfolio files directly in the external folder without editing the website again.
Other options
A public Notion portfolio page or Dropbox folder can be used instead. Paste that public URL into the same PORTFOLIO_LIBRARY_URL setting.
Important
Keep drafts/private review files out of the public folder until they are approved for publishing.
Portfolio library connected: https://drive.google.com/drive/folders/11NKFAENCXJTEHPwaUWsQvUImErH18HzS