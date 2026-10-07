from __future__ import annotations
import math

def shelf_nest(rectangles, stock_w, stock_h, gap=0, margin=0):
    """REVIEW-only shelf nesting. rectangles=[{'id','w','h','qty'}]. No rotation."""
    for name,value,positive in [('stock_w',stock_w,True),('stock_h',stock_h,True),('gap',gap,False),('margin',margin,False)]:
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or (value<=0 if positive else value<0):
            raise ValueError(f'{name} must be finite and {"positive" if positive else "nonnegative"}')
    sheets=[]; unplaced=[]
    expanded=[]
    for r in rectangles:
        if any(isinstance(r.get(k),bool) or not isinstance(r.get(k),(int,float)) or not math.isfinite(r[k]) or r[k]<=0 for k in ('w','h')):
            raise ValueError('blank dimensions must be finite positive numbers')
        if isinstance(r.get('qty',1),bool) or not isinstance(r.get('qty',1),int) or r.get('qty',1)<1:
            raise ValueError('blank quantity must be a positive integer')
        for i in range(int(r.get('qty',1))): expanded.append({'id':r['id'],'instance':i+1,'w':float(r['w']),'h':float(r['h'])})
    expanded.sort(key=lambda r:(-r['h'],-r['w']))
    for r in expanded:
        if r['w']+2*margin>stock_w or r['h']+2*margin>stock_h:
            unplaced.append({**r,'reason':'larger_than_stock'}); continue
        placed=False
        for s in sheets:
            x=s['cursor_x']; y=s['cursor_y']; shelf_h=s['shelf_h']
            if x+r['w']+margin<=stock_w and y+r['h']+margin<=stock_h:
                s['placements'].append({**r,'x':x,'y':y,'rotated':False}); s['cursor_x']=x+r['w']+gap; s['shelf_h']=max(shelf_h,r['h']); placed=True; break
            new_y=y+shelf_h+gap
            if margin+r['w']<=stock_w-margin and new_y+r['h']<=stock_h-margin:
                s['cursor_x']=margin+r['w']+gap; s['cursor_y']=new_y; s['shelf_h']=r['h']; s['placements'].append({**r,'x':margin,'y':new_y,'rotated':False}); placed=True; break
        if not placed:
            s={'sheet':len(sheets)+1,'cursor_x':margin+r['w']+gap,'cursor_y':margin,'shelf_h':r['h'],'placements':[{**r,'x':margin,'y':margin,'rotated':False}]}; sheets.append(s)
    for s in sheets:
        used=sum(p['w']*p['h'] for p in s['placements']); s['utilization']=used/(stock_w*stock_h); s.pop('cursor_x'); s.pop('cursor_y'); s.pop('shelf_h')
    return {'provider':'builtin-shelf-review','review_only':True,'manufacturing_release':False,'stock_mm':[stock_w,stock_h],'sheets':sheets,'unplaced':unplaced}
