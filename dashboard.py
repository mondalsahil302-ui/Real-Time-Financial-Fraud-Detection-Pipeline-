from http.server import BaseHTTPRequestHandler, HTTPServer
from cassandra.cluster import Cluster
from html import escape
from datetime import datetime

HOST = "127.0.0.1"
PORT = 8080

def get_data():
    cluster = Cluster(["127.0.0.1"])
    try:
        session = cluster.connect("fraud_detection")
        rows = list(session.execute(
            "SELECT transaction_id, amount, type, predicted_is_fraud, risk_level "
            "FROM transactions"
        ))
        processed = [r for r in rows if r.risk_level is not None]
        fraud = sum(r.predicted_is_fraud == 1 for r in processed)
        high = sum(r.risk_level == "HIGH" for r in processed)
        medium = sum(r.risk_level == "MEDIUM" for r in processed)
        low = sum(r.risk_level == "LOW" for r in processed)
        recent = list(reversed(processed[-20:]))
        return len(rows), len(processed), fraud, high, medium, low, recent
    finally:
        cluster.shutdown()

class Dashboard(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            total, processed, fraud, high, medium, low, recent = get_data()
            cards = [
                ("Total Transactions", total),
                ("Processed", processed),
                ("Pending", total - processed),
                ("Predicted Fraud", fraud),
                ("High Risk", high),
                ("Medium Risk", medium),
                ("Low Risk", low),
            ]
            card_html = "".join(
                f'<div class="card"><div class="label">{escape(str(k))}</div>'
                f'<div class="number">{v}</div></div>' for k, v in cards
            )
            table_rows = "".join(
                "<tr>"
                f"<td>{escape(str(r.transaction_id))}</td>"
                f"<td>{r.amount if r.amount is not None else '-'}</td>"
                f"<td>{escape(str(r.type or '-'))}</td>"
                f"<td>{r.predicted_is_fraud if r.predicted_is_fraud is not None else '-'}</td>"
                f"<td><span class='risk {escape(str(r.risk_level or 'PENDING').lower())}'>"
                f"{escape(str(r.risk_level or 'PENDING'))}</span></td></tr>"
                for r in recent
            )
            page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="10"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Real-Time Fraud Detection</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#0b1220;color:#edf2ff;font-family:Arial,sans-serif}}
header{{padding:28px 5%;background:#121d31;border-bottom:1px solid #263650}}
h1{{margin:0 0 8px;font-size:27px}}.sub{{color:#a9b9d3;font-size:14px}}
main{{padding:25px 5%}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:14px}}
.card{{background:#17243a;border:1px solid #293b58;border-radius:12px;padding:20px}}
.label{{color:#a9b9d3;font-size:13px}}.number{{font-size:30px;font-weight:bold;margin-top:12px}}
h2{{font-size:19px;margin-top:30px}}.tablebox{{overflow-x:auto;background:#17243a;border-radius:12px}}
table{{width:100%;border-collapse:collapse;min-width:650px}}th,td{{padding:13px;text-align:left;border-bottom:1px solid #293b58;font-size:13px}}
th{{color:#a9b9d3}}.risk{{font-weight:bold}}.high{{color:#ff7777}}.medium{{color:#ffca68}}.low{{color:#77e0b0}}.pending{{color:#a9b9d3}}
footer{{padding:20px 5%;color:#a9b9d3;font-size:12px}}
</style></head><body><header><h1>Real-Time Financial Fraud Detection</h1>
<div class="sub">Transaction monitoring dashboard · Auto-refreshes every 10 seconds</div></header>
<main><div class="cards">{card_html}</div><h2>Recent Processed Transactions</h2>
<div class="tablebox"><table><thead><tr><th>Transaction ID</th><th>Amount</th><th>Type</th><th>Predicted Fraud</th><th>Risk Level</th></tr></thead>
<tbody>{table_rows or '<tr><td colspan="5">No processed transactions yet.</td></tr>'}</tbody></table></div>
<p class="sub">Fraud predictions and risk levels are read from Cassandra. Prediction 1 = flagged by the model; 0 = not flagged.</p></main>
<footer>Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</footer></body></html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))
        except Exception as exc:
            self.send_error(500, "Dashboard error: " + str(exc))

print(f"Dashboard starting at http://localhost:{PORT}")
HTTPServer(("127.0.0.1", PORT), Dashboard).serve_forever()
