# Hot Reload Guide 🔥

DashML now supports hot reload! Edit your `.dashml` files and see changes instantly.

## Usage

### For Streamlit

**Terminal 1: Start watch mode**
```bash
cd dashml_new
python cli.py watch ../dashml_example.dashml --target streamlit --output ../app.py
```

**Terminal 2: Run Streamlit (from playground directory)**
```bash
cd ..
streamlit run app.py
```

**Now edit `dashml_example.dashml` and save** - the app will automatically rebuild!

Streamlit has built-in hot reload, so it will detect the regenerated `app.py` and refresh automatically.

### For Plotly

**Terminal 1: Start watch mode**
```bash
cd dashml_new
python cli.py watch ../dashml_example.dashml --target plotly --output ../dashboard.html
```

**Terminal 2: Serve with HTTP server (from playground directory)**
```bash
cd ..
python -m http.server 8000
```

**Now edit `dashml_example.dashml` and save** - the HTML will rebuild automatically.

You'll need to refresh your browser manually to see changes.

## What Happens

1. 👀 Watch mode monitors your `.dashml` file every 1 second
2. 🔄 When you save changes, it detects the modification
3. ✓ Validates the new spec
4. ✓ Generates new code
5. ✓ Writes to output file
6. 🎉 For Streamlit: auto-refreshes! For Plotly: refresh browser manually

## Example Output

```
👀 Watch mode: Generates Streamlit Python applications
📄 Input:  ../dashml_example.dashml
📝 Output: ../app.py

Building initial version...
✓ Spec validated
✓ Code generated (1234 chars)
✓ Written to ../app.py

[17:30:15] 👀 Watching ../dashml_example.dashml for changes...
Press Ctrl+C to stop

[17:30:42] 🔄 Change detected in dashml_example.dashml
✓ Spec validated
✓ Code generated (1256 chars)
✓ Written to ../app.py

[17:31:05] 🔄 Change detected in dashml_example.dashml
✓ Spec validated
✓ Code generated (1278 chars)
✓ Written to ../app.py
```

## Stopping Watch Mode

Press `Ctrl+C` to stop watching.

## Tips

### Streamlit + Watch = 🔥🔥🔥

This is the best combo! Both watch mode AND Streamlit have hot reload, so you get instant feedback:

1. Edit `.dashml` → Watch rebuilds `app.py`
2. `app.py` changes → Streamlit reloads browser
3. See changes instantly! 🚀

### Multiple Watches

You can run multiple watch commands in different terminals:

```bash
# Terminal 1: Watch for Streamlit
python cli.py watch dashboard.dashml --target streamlit --output app.py

# Terminal 2: Watch for Plotly (same source!)
python cli.py watch dashboard.dashml --target plotly --output index.html

# Terminal 3: Run Streamlit
streamlit run app.py

# Terminal 4: Serve Plotly
python -m http.server 8000
```

Now ONE `.dashml` file generates BOTH outputs on every save!

## Error Handling

If you make an error in your `.dashml` file, watch mode will show the error and keep watching:

```
[17:32:15] 🔄 Change detected in dashml_example.dashml
✗ Validation Error: Chart 'sales_chart' missing required field: 'y'
```

Fix the error, save again, and it will rebuild successfully.

## Performance

- Polling interval: 1 second (lightweight)
- Only rebuilds when file actually changes
- Fast regeneration (< 100ms typically)

Enjoy your hot reload! 🎉
