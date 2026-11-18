#!/bin/zsh
# English + Hinglish channels that post full episodes and official Shorts cut from them.
export SSL_CERT_FILE=~/.mac-ca-bundle.pem REQUESTS_CA_BUNDLE=~/.mac-ca-bundle.pem UV_SYSTEM_CERTS=1
run() { uv run --script tools/goldset/build.py "$@" 2>&1 | grep -E "episodes >|best match|gold pair|pair\(s\)|ERROR" }
run @TheDiaryOfACEO en --shorts 20 --episodes 25 --max-pairs 4
run @hubermanlab en --shorts 15 --episodes 20 --max-pairs 3 --genre genre.podcast_clip
run @aliabdaal en --shorts 15 --episodes 20 --max-pairs 3 --genre genre.talking_head
run @BeerBiceps hi --shorts 20 --episodes 25 --max-pairs 4
run @RajShamani hi --shorts 20 --episodes 25 --max-pairs 4
