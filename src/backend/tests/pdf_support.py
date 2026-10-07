"""Synthetic two-byte Unicode PDF fixtures; no real bank/customer data."""
import io
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,ArrayObject,NumberObject,DecodedStreamObject

def pdf_bytes(texts,*,encrypt=False,active=False):
 writer=PdfWriter()
 for text in texts:
  page=writer.add_blank_page(width=600,height=800)
  chars=list(dict.fromkeys(text));codes={c:n+1 for n,c in enumerate(chars)}
  cmap="/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /Test def /CMapType 2 def 1 begincodespacerange <0000> <FFFF> endcodespacerange\n"+str(len(chars))+" beginbfchar\n"+"\n".join(f"<{codes[c]:04X}> <{c.encode('utf-16-be').hex()}>" for c in chars)+"\nendbfchar endcmap CMapName currentdict /CMap defineresource pop end end"
  cm=DecodedStreamObject();cm.set_data(cmap.encode())
  cid=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/CIDFontType2'),NameObject('/BaseFont'):NameObject('/Test'),NameObject('/CIDSystemInfo'):DictionaryObject({NameObject('/Registry'):NameObject('/Adobe'),NameObject('/Ordering'):NameObject('/Identity'),NameObject('/Supplement'):NumberObject(0)})})
  font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type0'),NameObject('/BaseFont'):NameObject('/Test'),NameObject('/Encoding'):NameObject('/Identity-H'),NameObject('/DescendantFonts'):ArrayObject([writer._add_object(cid)]),NameObject('/ToUnicode'):writer._add_object(cm)})
  page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
  stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 30 750 Td <'+''.join(f'{codes[c]:04X}' for c in text)+'> Tj ET').encode());page[NameObject('/Contents')]=writer._add_object(stream)
 if encrypt:writer.encrypt('synthetic')
 if active:writer.add_js('app.alert(1)')
 out=io.BytesIO();writer.write(out);return out.getvalue()
