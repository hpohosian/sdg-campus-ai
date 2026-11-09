Third-party JavaScript bundled with local_ai_system (see ../thirdpartylibs.xml).

How to update (from any machine with npm):
  npm pack marked@<version> katex@<version> html2canvas@<version> jspdf@<version>
  marked:      package/marked.min.js                -> thirdparty/marked/
  katex:       package/dist/katex.min.js, katex.min.css -> thirdparty/katex/
               package/dist/fonts/*.woff2            -> thirdparty/katex/fonts/
  html2canvas: package/dist/html2canvas.min.js      -> thirdparty/html2canvas/
  jspdf:       package/dist/jspdf.umd.min.js        -> thirdparty/jspdf/
Copy the LICENSE file of each package next to it and update the versions
in ../thirdpartylibs.xml.
