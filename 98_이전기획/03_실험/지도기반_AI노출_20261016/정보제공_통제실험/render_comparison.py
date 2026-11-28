"""Plot observed contrasts with explicit fixed-corpus, repeated-trial scope."""
import csv
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.mpl-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    first=list(csv.DictReader((ROOT/'factor_effects.csv').open(encoding='utf-8-sig')))
    equal=list(csv.DictReader((ROOT/'동일정보_표현비교'/'factor_effects.csv').open(encoding='utf-8-sig')))
    items=[(first,'menu_price_detail','메뉴·가격 정보 추가',['업종·주소만','메뉴·가격 추가']),
           (equal,'structured_layout','모든 사실이 같을 때: 정리 방식',['한 문단','항목별 정리']),
           (equal,'keyword_repetition','모든 사실이 같을 때: 검색어 반복',['추가 반복 없음','지역·업종 3회 추가'])]
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':11})
    fig,axes=plt.subplots(1,3,figsize=(13.3,5.7),sharey=True)
    for ax,(rows,factor,title,labels) in zip(axes,items):
        r=next(x for x in rows if x['backend']=='ALL' and x['factor']==factor)
        values=[float(r['absent_rate'])*100,float(r['present_rate'])*100]
        bars=ax.bar([0,1],values,width=.6,color=['#A7ADB5','#2864A0'])
        bars[0].set_hatch('//')
        for bar,value in zip(bars,values):
            ax.text(bar.get_x()+bar.get_width()/2,value+2,f'{value:.1f}%\n{round(value*.96)}/96',ha='center',va='bottom',fontsize=11)
        ax.set_xticks([0,1],labels,fontsize=10);ax.set_ylim(0,115);ax.set_yticks(range(0,101,20))
        ax.set_title(title,fontsize=12,pad=13,fontweight='bold');ax.spines[['top','right']].set_visible(False)
        ax.axhline(50,color='#777777',lw=.7,ls=':')
    axes[0].set_ylabel('후보 선택 비율 (%)')
    fig.suptitle('제공된 지도 정보로 식당 후보를 고른 결과',x=.07,ha='left',fontweight='bold',fontsize=17)
    fig.text(.07,.08,'카카오맵 12곳 · 1차 48회 + 후속 48회 · 같은 식당 반복 관측 · 실제 지도 검색 노출과 별도',fontsize=11)
    fig.text(.07,.035,'정리 방식의 차이는 명동에서만 관측됨. 각 비율의 분모 96은 독립 식당 수가 아님.',fontsize=10,color='#555555')
    fig.subplots_adjust(top=.8,bottom=.24,left=.07,right=.98,wspace=.22)
    fig.savefig(ROOT/'실험비교.png',dpi=170);plt.close(fig)


if __name__=='__main__':main()
