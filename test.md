---
css: |
  body { background: #1e1e2e; color: #cdd6f4; }
  h1 { color: #cba6f7; }
  code {font-family: 'Menlo'; font-size: 20px;}
  .markdown-body pre {
      background-color: #1e1e1e;
      border: 1px solid #333333;
      border-radius: 8px;
      padding: 16px;
      margin: 20px 0;
      overflow-x: auto;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.15);
  }
  .markdown-body pre code {
      color: #9cdcfe;
      font-family: 'Fira Code', 'Courier New', Courier, monospace;
      font-size: 14px;
      line-height: 1.5;
      background: transparent;
      padding: 0;
  }
---

# My Document

Markdown content here...
```bash
ls -l
```
```python
print('Hello World..!')
```
```powershell
New-Item run.py
```
```go
package main
import "fmt"
func main() {
    fmt.Println("Hello, World!")
}
```
To print text in `go`, you use the `fmt.Println()` function.
