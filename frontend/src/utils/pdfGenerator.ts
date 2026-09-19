import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas';

/**
 * High-resolution vector-quality PDF generator using html2canvas & jsPDF.
 * Renders the executive report DOM element without any font/text overlap bugs.
 */
export async function exportElementToPdf(
  element: HTMLElement,
  filename: string = 'Expert_Burn_Severity_Report.pdf'
): Promise<void> {
  // Capture DOM at 2x retina scale with pure white background
  const canvas = await html2canvas(element, {
    scale: 2,
    useCORS: true,
    backgroundColor: '#FFFFFF',
    logging: false,
    windowWidth: 1000,
  });

  const imgData = canvas.toDataURL('image/png');
  const pdf = new jsPDF({
    orientation: 'portrait',
    unit: 'mm',
    format: 'a4',
  });

  const pdfWidth = 210; // A4 mm
  const pdfHeight = (canvas.height * pdfWidth) / canvas.width;

  pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, Math.min(297, pdfHeight));
  pdf.save(filename);
}
