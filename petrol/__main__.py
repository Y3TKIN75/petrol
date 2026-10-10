import argparse
import sys

from . import collect, pipeline
from .config import POLL_INTERVAL_SEC
from .llm import LLMError
from .report import print_report


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="petrol")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_collect = sub.add_parser("collect", help="Sadece kaynaklari tarar ve veritabanina yazar")
    p_collect.add_argument("--once", action="store_true", help="Tek tur calis ve cik")
    p_collect.add_argument("--interval", type=int, default=POLL_INTERVAL_SEC, help="Tarama araligi (sn)")

    p_run = sub.add_parser("run", help="Tam dongu: tara + AI filtre + analiz")
    p_run.add_argument("--once", action="store_true", help="Tek tur calis ve cik")
    p_run.add_argument("--interval", type=int, default=POLL_INTERVAL_SEC, help="Tarama araligi (sn)")
    p_run.add_argument("--no-collect", action="store_true", help="Taramayi atla, sadece bekleyenleri isle")

    p_signals = sub.add_parser("signals", help="Son sinyalleri listeler")
    p_signals.add_argument("--all", action="store_true", help="Gunluk ozet seviyesini de goster")
    p_signals.add_argument("-n", type=int, default=20)

    sub.add_parser("report", help="Kaynak gecikme, hacim ve AI kullanim raporu")

    p_bt = sub.add_parser("backtest", help="Arsiv haberleriyle geriye donuk test")
    p_bt.add_argument("--cases", default="arastirma/backtest/vakalar.json")
    p_bt.add_argument("--split", choices=["all", "kalibrasyon", "test"], default="all")
    p_bt.add_argument("--calibration", default=None, help="Analiz istemine eklenecek kalibrasyon dosyasi")
    p_bt.add_argument("--label", default="deneme")
    p_bt.add_argument("--reserve", type=int, default=20000, help="Canli akis icin birakilacak token payi")
    p_bt.add_argument("--dry-run", metavar="VAKA_ID", default=None, help="API cagirmadan istemi goster")
    p_bt.add_argument("--ids", default=None, help="Yalnizca bu vakalar (virgulle: H1,H4)")
    p_bt.add_argument("--triage-only", type=int, metavar="TEKRAR", default=0,
                      help="Yalnizca filtreyi N kez calistir ve gecis oranlarini goster")

    p_imp = sub.add_parser("import-analyses", help="Disarida yapilmis analizleri JSON'dan aktar")
    p_imp.add_argument("file")
    p_imp.add_argument("--backup", default=None, help="Mevcut analizlerin yedeklenecegi dosya")

    args = parser.parse_args()
    try:
        if args.cmd == "collect":
            # 'run' ile ayni kilidi paylasir: ayni kaynaklar iki kez taranmasin
            lock = pipeline.acquire_single_instance_lock()
            if lock is None:
                print("Baska bir dongu zaten calisiyor; cikiliyor.")
                sys.exit(2)
            collect.run(once=args.once, interval=args.interval)
        elif args.cmd == "run":
            pipeline.run(once=args.once, interval=args.interval, collect=not args.no_collect)
        elif args.cmd == "signals":
            pipeline.print_signals(limit=args.n, include_digest=args.all)
        elif args.cmd == "report":
            print_report()
        elif args.cmd == "import-analyses":
            import json
            from pathlib import Path

            from .db import connect
            from .manual import apply_manual_analyses, backup_analyses
            conn = connect()
            src = Path(args.file)
            backup = Path(args.backup) if args.backup else src.with_name(src.stem + "_oncesi_yedek.json")
            print(f"Mevcut {backup_analyses(conn, backup)} analiz yedeklendi: {backup}")
            for r in apply_manual_analyses(conn, json.loads(src.read_text(encoding="utf-8"))):
                print(f"  {pipeline.LEVEL_ICON[r['level']]} {r['score']:>3} {pipeline.ARROW[r['yon']]} "
                      f"E{r['event_id']} {r['title'][:90]}")
        elif args.cmd == "backtest":
            from pathlib import Path

            from .backtest import print_result, run_backtest, triage_eval
            if args.triage_only:
                triage_eval(Path(args.cases), args.triage_only, args.reserve)
                return
            out = run_backtest(Path(args.cases), args.split, Path(args.calibration) if args.calibration else None,
                               args.label, args.reserve, dry_run=args.dry_run,
                               only_ids=set(args.ids.split(",")) if args.ids else None)
            if out:
                print_result(out)
    except KeyboardInterrupt:
        print("durduruldu")
    except LLMError as exc:
        print(f"AI hatasi: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
