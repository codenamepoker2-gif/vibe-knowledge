import Vision
import AppKit
// 第一个参数可以是 --langs=th-TH,en-US（qa.py --lang th 时传）；默认简体中文 + 英文
// Optional first argument --langs=th-TH,en-US (qa.py passes it for Thai); default zh-Hans + en-US.
var args = Array(CommandLine.arguments.dropFirst())
var langs = ["zh-Hans", "en-US"]
if let first = args.first, first.hasPrefix("--langs=") {
  langs = first.dropFirst("--langs=".count).split(separator: ",").map(String.init)
  args.removeFirst()
}
for path in args {
  guard let img = NSImage(contentsOfFile: path), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
  let req = VNRecognizeTextRequest()
  req.recognitionLevel = .accurate
  req.recognitionLanguages = langs
  req.usesLanguageCorrection = true
  try? VNImageRequestHandler(cgImage: cg).perform([req])
  let obs = (req.results ?? []).sorted { $0.boundingBox.minY > $1.boundingBox.minY }
  let lines = obs.compactMap { o -> String? in
    guard let t = o.topCandidates(1).first, t.confidence > 0.4 else { return nil }
    let b = o.boundingBox
    return String(format: "[y%.2f h%.3f] ", b.minY, b.height) + t.string }
  print("@@" + (path as NSString).lastPathComponent)
  lines.forEach { print($0) }
}
