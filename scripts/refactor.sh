mv scripts/discord_listener.py src/drunken_agy/services/discord_listener.py
mv scripts/serve_dashboard.py src/drunken_agy/routes/serve_dashboard.py

cat << 'INNER_EOF' > scripts/discord_listener.py
#!/usr/bin/env python3
import sys
from drunken_agy.services.discord_listener import main

if __name__ == "__main__":
    sys.exit(main())
INNER_EOF
chmod +x scripts/discord_listener.py

cat << 'INNER_EOF' > scripts/serve_dashboard.py
#!/usr/bin/env python3
import sys
from drunken_agy.routes.serve_dashboard import main

if __name__ == "__main__":
    sys.exit(main())
INNER_EOF
chmod +x scripts/serve_dashboard.py
