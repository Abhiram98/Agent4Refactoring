import os
import json
from pathlib import Path
from email.message import EmailMessage
from email.utils import make_msgid
import mimetypes

def attach_inline_image(msg, img_path, cid):
    with open(img_path, 'rb') as img:
        maintype, subtype = mimetypes.guess_type(img_path)[0].split('/')
        # Attach to the HTML part (the last alternative part)
        msg.get_payload()[-1].add_related(
            img.read(),
            maintype=maintype,
            subtype=subtype,
            cid=cid,
            filename=os.path.basename(img_path)
        )

def generate_html_email(developer_name, stats, weekly_img_cid, heatmap_img_cid, commit_url, entity_count, commit_count, total_renames_in_the_commit, renamed_attributes):
    # Build HTML for renamed attributes
    renamed_html = ""
    if renamed_attributes:
        renamed_html += '<p>The commit below contains a cluster of related renames:</p>'
        renamed_html += f'<a href="{commit_url}">{commit_url}</a>'
        renamed_html += '<ul>'
        for attr in renamed_attributes:
            code_element = attr.get('code_element', '')
            rename = attr.get('rename', '')
            renamed_html += f'<li><b>{code_element}</b>: {rename}</li>'
        renamed_html += '</ul>'
    return f"""
    <html>
    <body style="font-family: 'Times New Roman', Times, serif; font-size: 16px;">
    <p>Hello {get_first_name(developer_name)},</p>
    <p>
    We are researchers from the University of Colorado Boulder, conducting a study to understand patterns and challenges in <b>cluster-renames</b>—situations where <b>multiple related program elements are renamed together in the same commit</b>.<br>
    <b>Our goal is to learn how developers approach these cluster-renames and whether parts of this process can be supported or automated through better tools.</b>
    </p>
    <p>
    We analyzed the <b>{stats['dataset_statistics']['total_analyzed_commit']}</b> most recent commits in <b>{stats['analysis_metadata']['project_name']}</b> and identified <b>{stats['dataset_statistics']['total_rename_commit']}</b> commits that involved renaming. Among these rename commits, <b>{stats['dataset_statistics']['total_co_rename_commit']} commits ({stats['dataset_statistics']['co_rename_precentage']}%)</b> contained cluster-rename instances. For these cluster-rename commits, we further analyzed the number of renamed entities per commit and found the following distribution:
    </p>
    <ul>
      <li>Mean: <b>{stats['rename_statistics']['mean']}</b> renames per commit</li>
      <li>Median: <b>{stats['rename_statistics']['median']}</b> renames per commit</li>
      <li>Maximum: <b>{stats['rename_statistics']['max']}</b> renames in a single commit</li>
    </ul>
    <p>
    The figures below show an overview of cluster-rename activity in <b>{stats['analysis_metadata']['project_name']}</b> on a weekly basis:
    </p>
    <table cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td style="width:320px; height:180px; text-align:center; vertical-align:middle;">
          <img src="cid:{weekly_img_cid[1:-1]}" width="320" height="180" style="display:block; width:100%; height:100%; border:1px solid #ccc;">
        </td>
        <!-- Spacer cell for gap -->
        <td style="width:16px;"></td>
        <td style="width:320px; height:180px; text-align:center; vertical-align:middle;">
          <img src="cid:{heatmap_img_cid[1:-1]}" width="320" height="180" style="display:block; width:100%; height:100%; border:1px solid #ccc;">
        </td>
      </tr>
    </table>
    <p style="margin-top: 32px;">We are reaching out to you because you are one of the most active contributors in commits with high cluster-rename activity. <span><b>{get_first_name(developer_name)}</b></span>, you renamed <span><b>{entity_count} entities across {commit_count} commits</b></span>.</p>
    <p>
    {gratitude_sentence(renamed_attributes, total_renames_in_the_commit)}<br>
    <a href="{commit_url}">{commit_url}</a>:
    </p>
    <ul style="margin-top:0; margin-bottom:0;">
    {''.join([f'<li>{format_rename_instance(attr)}</li>' for attr in renamed_attributes])}
    </ul>
    <p>{cluster_rename_sentence(renamed_attributes, total_renames_in_the_commit)}</p>
    <ul>
      <li><b>Q1.</b> How long did it take you to identify the <b>{total_renames_in_the_commit}</b> related program elements (e.g., fields, classes, enums) that form a concept / cluster and should be renamed together as part of this cluster-rename?</li>
      <li><b>Q2.</b> Was this cluster-rename challenging to perform or review? For example, identifying which program elements (fields, methods, classes, variables, etc) should change together, etc. What are some other challenges?</li>
      <li><b>Q3.</b> Was this cluster-rename performed manually or using automated tools (or both)? Would it be helpful to have tools that assist in automatically identifying such related program elements and renaming the whole cluster in one step, rather than renaming them individually?</li>
    </ul>
    <p>
    Your responses will remain <b>anonymous</b> and will be used solely for research purposes. We sincerely appreciate your time and contribution. If you're interested in the results of our study, let us know, and we'll be happy to share them with you once the research is complete.
    </p>
    <p>
    If you have any additional thoughts or experiences related to cluster-renaming or refactoring in large codebases, we'd love to hear them as well.
    </p>
    <p>
    Warm regards,<br>
    Raihan Ullah<br>
    Ph.D. Student<br>
    Department of Computer Science<br>
    University of Colorado Boulder, USA
    </p>
    </body>
    </html>
    """

# Helper function for formatting rename instances
def format_rename_instance(attr):
    code_element = attr.get('code_element', '')
    rename = attr.get('rename', '')
    if '->' in rename:
        before, after = [s.strip() for s in rename.split('->', 1)]
        return f'{code_element} <i><b>{before}</b></i> -> <i><b>{after}</b></i>.'
    elif ' to ' in rename:
        before, after = [s.strip() for s in rename.split(' to ', 1)]
        return f'{code_element} <i><b>{before}</b></i> -> <i><b>{after}</b></i>.'
    else:
        return f'{code_element}: <i><b>{rename}</b></i>.'

def gratitude_sentence(renamed_attributes, total_renames_in_the_commit):
    if len(renamed_attributes) >= 2:
        return f"We would be grateful if you could help answer a few questions about your recent commit that contains <b>{total_renames_in_the_commit}</b> renames grouped into multiple clusters:"
    else:
        return f"We would be grateful if you could help answer a few questions about your recent commit that contains a cluster of <b>{total_renames_in_the_commit}</b> renames:"

# Helper to extract first name
def get_first_name(full_name):
    return full_name.split()[0] if full_name else "Developer"

# Helper for cluster rename explanatory sentence
def cluster_rename_sentence(renamed_attributes, total_renames_in_the_commit):
    if len(renamed_attributes) >= 2:
        return "We refer to all of these renames as cluster renames. Below, we ask questions about this cluster rename."
    else:
        return f"We refer to all these {total_renames_in_the_commit} renames as a single cluster rename."

def main():
    # Paths (edit as needed)
    analysis_dir = Path("refagent/utils/analyze_and_send_email/analyze/refactoring_results_bazel")
    developer_analysis_dir = analysis_dir / "developer_analysis"
    plot_dir = analysis_dir / "plots"
    weekly_img = plot_dir / "weekly_rename_activity.png"
    heatmap_img = plot_dir / "heatmap.png"
    developer_json = list(developer_analysis_dir.glob("*.json"))[0]
    commit_url = "https://github.com/bytechef/bytechef/commit/3a7c5e123c6262fc8f26fdcb7c5a8383864"
    entity_count = 1900
    commit_count = 181

    # Load stats
    with open(developer_json, "r") as f:
        stats = json.load(f)
    developer_name = stats.get("developer_name", "Developer")
    developer_email = "developer@example.com"  # Set as needed

    # Prepare email
    msg = EmailMessage()
    msg['Subject'] = f"Study on Cluster-Renames in {stats['analysis_metadata']['project_name']}"
    msg['From'] = "Raihan Ullah <Raihan.Ullah@colorado.edu>"
    msg['To'] = developer_email

    # Generate Content-IDs for images
    weekly_img_cid = make_msgid(domain="inline")
    heatmap_img_cid = make_msgid(domain="inline")

    # Set HTML body
    html = generate_html_email(
        developer_name, stats, weekly_img_cid, heatmap_img_cid, commit_url, entity_count, commit_count, total_renames_in_the_commit, renamed_attributes
    )
    msg.set_content("This email contains HTML content. Please view in an HTML-compatible email client.")
    msg.add_alternative(html, subtype='html')

    # Attach images inline
    attach_inline_image(msg, weekly_img, weekly_img_cid)
    attach_inline_image(msg, heatmap_img, heatmap_img_cid)

    # Save as .eml draft
    with open("email_draft.eml", "wb") as f:
        f.write(bytes(msg))
    print("Email draft with inline images saved as email_draft.eml")

if __name__ == "__main__":
    main()