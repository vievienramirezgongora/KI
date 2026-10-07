import argparse
import json

from .pipeline import Pipeline


def main():
    parser = argparse.ArgumentParser(description="Tukey, Z-score and Modified Z-score")
    parser.add_argument("--config", required=True, help="Pipeline JSON configuration")
    parser.add_argument("--input", help="Override data path, relative to the current directory")
    parser.add_argument("--extractor", help="Named extractor from the extractor configuration")
    args = parser.parse_args()
    try:
        result = Pipeline(args.config, input_path=args.input, extractor=args.extractor).run()
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    except (ValueError, OSError, TypeError, OverflowError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
