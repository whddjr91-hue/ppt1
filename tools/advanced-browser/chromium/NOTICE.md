# Chromium distribution notices

- Package: @sparticuz/chromium 153.0.0, https://github.com/Sparticuz/chromium (MIT; full text in LICENSE).
- Documentation reviewed at commit 2755b27e7a8654dbbc69eb2f9a728db6f3812e81. This does not assert the npm binary's source build commit. npm archive identity is pinned by SHA512 in package-lock.json; extracted executable identity is pinned by SHA256 in the preparation/runtime helpers.
- Browser reports Chromium 153.0.8010.0. Chromium base license is BSD-3-Clause (CHROMIUM-LICENSE); upstream source https://github.com/chromium/chromium. Chromium incorporates third-party components with their own licenses; upstream notices/source remain applicable. This repository does not redistribute the browser binary or claim every third-party license is MIT.
- Package's tar-fs dependencies retain license notices in node_modules. npm installation uses --ignore-scripts. No upstream package source was changed.
- Local extraction preserves current ownership using tar-fs chown:false because chown is not implemented by the workspace filesystem. Path and symlink checks remain enabled. Large generated runtime files live under node_modules/.cache; source/cache syncing had truncated an earlier executable. Preparation and every capture verify full executable length and SHA256.
- Linux x64 only. Node ^22.17.0 or >=24.0.0. Browser153 differs from Playwright1.62.1's official browser151: the actual basic capture workflow was tested, not every browser feature.
