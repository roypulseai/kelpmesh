# Data Processing Agreement (DPA)

**This DPA forms part of the Terms of Service between KelpMesh ("Processor") and the Customer ("Controller").**
**Governed by the Swiss Federal Act on Data Protection (nFADP / revDSG) and the EU General Data Protection Regulation (GDPR).**

## 1. Definitions

- **Personal Data**: as defined by nFADP Art. 5 lit. a and GDPR Art. 4(1)
- **Processing**: any operation performed on Personal Data (nFADP Art. 5 lit. c, GDPR Art. 4(2))
- **Controller**: the entity that determines the purposes of processing (nFADP Art. 5 lit. j, GDPR Art. 4(7))
- **Processor**: KelpMesh, processing data on behalf of the Controller (nFADP Art. 5 lit. i, GDPR Art. 4(8))
- **Data Subject**: the natural person whose data is processed

## 2. Processing Details

| Field | Value |
|-------|-------|
| **Categories of data subjects** | Customer's employees, contractors, and end users |
| **Types of personal data** | Email addresses, names, IP addresses |
| **Purpose of processing** | Providing the KelpMesh Service (SQL transformation, orchestration, documentation) |
| **Processing duration** | Duration of the agreement + 90 days |
| **Sub-processors** | AWS (EU & Swiss regions), Stripe (payment processing) |

## 3. Obligations of the Processor

KelpMesh shall:
- Process Personal Data only on documented instructions from the Controller (nFADP Art. 9, GDPR Art. 28(3))
- Ensure persons authorized to process the data have committed to confidentiality (nFADP Art. 6)
- Implement appropriate technical and organizational measures (see Section 7)
- Assist the Controller in fulfilling data subject rights (nFADP Art. 25, GDPR Art. 12-23)
- Delete or return all Personal Data at the end of the service
- Maintain a record of all processing activities (nFADP Art. 12, GDPR Art. 30)
- Notify the Controller of any Personal Data breach within 48 hours (nFADP Art. 24, GDPR Art. 33)

## 4. Data Subject Rights

KelpMesh shall promptly notify the Controller of any request from a Data Subject. KelpMesh will assist the Controller in responding to such requests within the timeframes required by applicable law (nFADP Art. 25, GDPR Art. 12).

Requests may be submitted via the Studio API:
- `GET /api/account/export` — data portability (nFADP Art. 28, GDPR Art. 20)
- `DELETE /api/account` — erasure (nFADP Art. 8, GDPR Art. 17)

## 5. Data Breach

KelpMesh shall notify the Controller within 48 hours of becoming aware of a Personal Data breach. Notification shall include:
- Nature of the breach
- Categories and approximate number of data subjects affected
- Contact point for further information
- Measures taken or proposed to address the breach

If the breach is likely to result in a high risk to data subjects, KelpMesh shall also assist the Controller in notifying the affected individuals (nFADP Art. 24, GDPR Art. 34).

## 6. Sub-processors

Current sub-processors:
- **Amazon Web Services** (EU & Swiss regions) — infrastructure hosting
- **Stripe** — payment processing (no personal data shared beyond email)

The Controller authorizes these sub-processors. KelpMesh will notify the Controller 30 days before engaging any new sub-processor.

## 7. Technical and Organizational Measures

KelpMesh implements the following measures in accordance with nFADP Art. 8 and GDPR Art. 32:

| Category | Measures |
|----------|----------|
| **Encryption at rest** | Fernet (AES-128-CBC + HMAC-SHA256) via `KELPMESH_ENCRYPTION_KEY` (state DB); RDS/S3 server-side encryption (Studio) |
| **Encryption in transit** | TLS 1.2+ for all network communication |
| **Access controls** | Least privilege principle; role-based access (admin/editor/viewer); API key authentication |
| **Secrets management** | Built-in `kelpmesh scan secrets` CLI command to detect hardcoded credentials |
| **Telemetry prohibition** | Runtime guard: any telemetry package detected at startup blocks execution |
| **Pseudonymisation** | Model hashes in state DB are SHA-256; personal data in run history is a project-level concern |
| **Incident response** | Documented plan; 48-hour breach notification commitment |
| **Employee access** | Background checks; access logged and audited quarterly |
| **Data minimization** | CLI collects nothing; Studio collects only what is necessary for the service |
| **Audit logging** | All API access logged with timestamp, action, and user ID |

## 8. Swiss Representative (Art. 14 nFADP)

For data subjects and authorities in Switzerland:

**KelpMesh GmbH**
Bahnhofstrasse 10
8001 Zurich, Switzerland
roypulse.ai@gmail.com

## 9. Governing Law and Disputes

This DPA is governed by **Swiss law**, with primary reference to the **Federal Act on Data Protection (nFADP / revDSG)** and, where applicable, the **EU GDPR**.

Any disputes shall be resolved in **Zurich, Switzerland**. The Controller may also lodge a complaint with the **Federal Data Protection and Information Commissioner (FDPIC)**.

## 10. Contact

- Data Protection Officer: **roypulse.ai@gmail.com**
- Swiss representative (Art. 14 nFADP): **KelpMesh GmbH, Bahnhofstrasse 10, 8001 Zurich, Switzerland**
- Security: **roypulse.ai@gmail.com**

---

*To execute this DPA, email roypulse.ai@gmail.com with your company name and account details.*
